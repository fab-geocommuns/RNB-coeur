from django.db import connection

from batid.utils.db import dictfetchall


def get_bdg_history(rnb_id: str) -> list[dict]:

    q = """
    SELECT
    bdg.rnb_id,
    bdg.is_active,
    ST_AsGeoJSON(bdg.shape)::json AS shape,
    bdg.status,
    bdg.ext_ids::json,
    lower(bdg.sys_period) AS updated_at,

    -- The addresses part
    (
        SELECT COALESCE(json_agg(
            json_build_object(
                'id', adr.id,
                'source', adr.source,
                'street_number', adr.street_number,
                'street_rep', adr.street_rep,
                'street', adr.street,
                'city_name', adr.city_name,
                'city_zipcode', adr.city_zipcode,
                'city_insee_code', adr.city_insee_code
            )
        ), '[]'::json)
        FROM public.batid_address AS adr
        WHERE adr.id = ANY(bdg.addresses_id)
    ) as addresses,

    -----------------------
    -----------------------
    -- The big hairy 'event' part
    -- 'event' is a custom object built in the query since the source data is located in multiple tables
    -- and has different format depending on the event type and origin

    json_build_object(
    	'id', bdg.event_id,
    	'type', bdg.event_type,

        ----------------------
        -- The event author
    	'author',
    	case
    		when u.id is not null
	    	then json_build_object(
    			'id', u.id,
                'username', u.username,
    			'first_name', u.first_name,
    			'last_name',
	    		case
	    			when u.last_name is not null and u.last_name <> ''
	    			then substring(u.last_name, 1, 1) || '.' else null
	    		end,
	    		'organizations_names', (
                    SELECT json_agg(org.name)
                    FROM batid_organization_users AS uo
                    JOIN batid_organization AS org ON uo.organization_id = org.id
                    WHERE uo.user_id = u.id
                )
	    	) else null
	    end,

        ----------------------
        -- The event origin
        -- is it a contribution, an import, a data fix, etc.

	    'origin',
	    json_build_object(
	    	'type', bdg.event_origin ->> 'source',
	    	'id',
	    	case
	    		when bdg.event_origin ->> 'source' = 'contribution'
	    		then (bdg.event_origin ->> 'contribution_id')::bigint
	    		else (bdg.event_origin ->> 'id')::bigint
	    	end,
	    	'details',
	    	case
	    		WHEN bdg.event_origin ->> 'source' = 'import'
	    		then (
	    			select json_build_object
	    			(
	    				'imported_database', imp.import_source
	    			) from batid_buildingimport as imp where imp.id = (bdg.event_origin ->> 'id')::int
	    		)
	    		when bdg.event_origin ->> 'source' = 'data_fix'
	    		then (
	    			select json_build_object (
	    				'description', fix.text
	    			) from batid_datafix fix where fix.id = (bdg.event_origin ->> 'id')::int
	    		)
	    		when bdg.event_origin ->> 'source' = 'contribution'
	    		then (
	    			select json_build_object
	    			(
	    				'is_report', con.report,
	    				'report_text', con.text,
	    				'review_comment', con.review_comment,
	    				'posted_on', con.rnb_id
	    			) from batid_contribution as con where con.id = (bdg.event_origin ->> 'contribution_id')::bigint
	    		)
	    		else null

	    	end
	    ),

        ----------------------
        -- The event details
        -- some relevant information about the event, depending on the event type and the source

	    'details',
	    case
            -- The row is a an update
			-- We attach previous and current versions of the building to calculate the diff
            -- The diff is done by Python in the serializer
	    	when bdg.event_type = 'update'
	    	then json_build_object(
	    		'previous_version', json_build_object(
	    			'status', prev_data.status,
	    			'shape', prev_data.shape,
	    			'ext_ids', prev_data.ext_ids,
	    			'addresses_id', prev_data.addresses_id
	    		),
                'current_version', json_build_object(
	    			'status', bdg.status,
	    			'shape', bdg.shape,
	    			'ext_ids', bdg.ext_ids,
	    			'addresses_id', bdg.addresses_id
                )
	    	)

            -- The row is a merge child
	    	when bdg.event_type = 'merge' and bdg.is_active -- We are looking the merge child
	    	then (
	    		select json_build_object(
	    			'merge_child', bdg.rnb_id,
	    			'merge_parents', bdg.parent_buildings
	    		)
	    	)

            -- The row is a merge parent
	    	when bdg.event_type = 'merge' and not bdg.is_active -- We are looking a merge parent
	    	then (
	    		SELECT json_build_object(
		            'merge_child', mc.rnb_id,
    		        'merge_parents', mc.parent_buildings
	        	)
				 FROM batid_building_with_history AS mc
				 WHERE mc.event_id = bdg.event_id AND mc.is_active
				 LIMIT 1
			)

            -- The row is a split child
	    	when bdg.event_type = 'split' and bdg.is_active -- We are looking a split child
	    	then (
            	select json_build_object(
	    		'split_parent', bdg.parent_buildings ->> 0,
	    		'split_children', (select coalesce(json_agg(sc.rnb_id), '[]'::json) from batid_building_with_history sc where sc.is_active and sc.event_id = bdg.event_id)
	    		)
            )

            -- The row is a split parent
	    	when bdg.event_type = 'split' and not bdg.is_active -- We are looking the split parent
	    	then (
				select json_build_object(
					'split_parent', bdg.rnb_id,
					'split_children', (select coalesce(json_agg(sc.rnb_id), '[]'::json) from batid_building_with_history sc where sc.is_active and sc.event_id = bdg.event_id)
				)
            )


	    end

    ) as event
    FROM batid_building_with_history as bdg
    left join auth_user as u on bdg.event_user_id  = u.id
    LEFT JOIN LATERAL (
		SELECT
			prev.rnb_id, prev.status, prev.shape, prev.ext_ids, prev.addresses_id
		FROM batid_building_with_history AS prev
		WHERE prev.rnb_id = bdg.rnb_id
		AND lower(prev.sys_period) < lower(bdg.sys_period)
		ORDER BY lower(prev.sys_period) DESC
		LIMIT 1
	) AS prev_data ON TRUE
    WHERE bdg.rnb_id = %(rnb_id)s
    ORDER BY lower(sys_period) DESC
    """

    params = {"rnb_id": rnb_id}

    with connection.cursor() as cursor:

        return dictfetchall(cursor, q, params)

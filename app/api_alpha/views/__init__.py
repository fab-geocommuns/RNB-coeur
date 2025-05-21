def get_schema(request):
    schema_dict = build_schema_dict()
    schema_yml = yaml.dump(
        schema_dict, default_flow_style=False, allow_unicode=True, sort_keys=False
    )

    response = HttpResponse(schema_yml, content_type="application/x-yaml")
    response["Content-Disposition"] = 'attachment; filename="schema.yml"'

    return response

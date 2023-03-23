from db import conn

def sandbox():

    with conn.cursor() as cursor:

        cursor.execute('SELECT * FROM batid_building LIMIT 100')

        for row in cursor.fetchall():
            print(row)


    pass



if __name__ == '__main__':
    sandbox()
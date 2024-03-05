from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pyodbc
import os
from gevent.pywsgi import WSGIServer

app = Flask(__name__)

# Configuración de límites de solicitud
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["5 per minute"])

# Configuración de la conexión a SQL Server
server = os.environ.get('DB_SERVER', '35.188.180.39')
database = os.environ.get('DB_DATABASE', 'glm_test')
username = os.environ.get('DB_USERNAME', 'sqlserver')
password = os.environ.get('DB_PASSWORD', '8unwsOsaBhIq6cm1')
driver = '{ODBC Driver 17 for SQL Server}'

# Establecer la conexión
conn_str = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

# Función para validar los headers y obtener permisos
def validate_headers():
    client_id = request.headers.get('client-id')
    client_secret = request.headers.get('client-secret')
    client_name = request.headers.get('client-name')
    organization = request.headers.get('organization')
    scope = request.headers.get('scope')

    # Log en lugar de print
    app.logger.debug(f"client_id: {client_id}")
    app.logger.debug(f"client_secret: {client_secret}")
    app.logger.debug(f"client_name: {client_name}")
    app.logger.debug(f"organization: {organization}")
    app.logger.debug(f"scope: {scope}")

    try:
        # Consulta parametrizada para evitar SQL injection
        cursor.execute('SELECT * FROM oauth WHERE client_secret = ?', client_secret)
        oauth_data = cursor.fetchone()

        if oauth_data:
            # Obtener los valores de los permisos de manera segura
            read_permission = getattr(oauth_data, 'lectura', 0) == 1
            create_permission = getattr(oauth_data, 'creacion', 0) == 1
            edit_permission = getattr(oauth_data, 'escritura', 0) == 1
            delete_permission = getattr(oauth_data, 'eliminacion', 0) == 1

            # Log de permisos
            app.logger.debug(f"read_permission: {read_permission}")
            app.logger.debug(f"create_permission: {create_permission}")
            app.logger.debug(f"edit_permission: {edit_permission}")
            app.logger.debug(f"delete_permission: {delete_permission}")

            # Resto del código de validación de headers...

            # Retornar los permisos adicionales
            return read_permission, create_permission, edit_permission, delete_permission
        else:
            # Si no se encuentra la información en la tabla oauth, considerar como inválido
            return False, False, False, False
    except Exception as e:
        # Log de errores
        app.logger.error(f"Error en la validación de headers: {str(e)}")
        return False, False, False, False

# Rutas de la API
# Obtener todos los registros de una tabla
@app.route('/table/<string:table_name>', methods=['GET'])
@limiter.limit("10 per minute")  # Límite adicional para esta ruta
def get_all_records(table_name):
    try:
        read_permission, create_permission, edit_permission, delete_permission = validate_headers()

        if not read_permission:
            return jsonify({'error': 'No tiene permisos de lectura.'}), 403

        query = f'SELECT * FROM {table_name}'
        cursor.execute(query)
        rows = cursor.fetchall()

        # Log de nombres de columnas
        app.logger.debug([column[0] for column in cursor.description])

        # Convertir los resultados a formato JSON
        records = [{column[0]: value for column, value in zip(cursor.description, row)} for row in rows]
        return jsonify(records)
    except Exception as e:
        # Log de errores
        app.logger.error(f"Error al obtener todos los registros: {str(e)}")
        return jsonify({'error': 'Error interno en el servidor.'}), 500

# Obtener un registro por ID de una tabla
@app.route('/table/<string:table_name>/<int:record_id>', methods=['GET'])
def get_record_by_id(table_name, record_id):
    try:
        read_permission, create_permission, edit_permission, delete_permission = validate_headers()

        if not read_permission:
            return jsonify({'error': 'No tiene permisos de lectura.'}), 403

        query = f'SELECT * FROM {table_name} WHERE ID = ?'
        cursor.execute(query, record_id)
        row = cursor.fetchone()

        if row:
            record = {column[0]: value for column, value in zip(cursor.description, row)}
            return jsonify(record)
        else:
            return jsonify({'error': f'Record with ID {record_id} not found in {table_name}'}), 404
    except Exception as e:
        # Log de errores
        app.logger.error(f"Error al obtener el registro por ID: {str(e)}")
        return jsonify({'error': 'Error interno en el servidor.'}), 500

# Crear un nuevo registro en una tabla
@app.route('/table/<string:table_name>', methods=['POST'])
def create_record(table_name):
    try:
        _, create_permission, _, _ = validate_headers()

        if not create_permission:
            return jsonify({'error': 'No tiene permisos de creación.'}), 403

        data = request.json  # Suponemos que los datos se envían en formato JSON en el cuerpo de la solicitud

        # Validar y sanitizar las entradas
        if not all(isinstance(key, str) and isinstance(value, (str, int, float, bool)) for key, value in data.items()):
            return jsonify({'error': 'Datos no válidos.'}), 400

        columns = ', '.join(data.keys())
        values = ', '.join(['?' for _ in data.values()])

        # Consultas parametrizadas
        query_insert = f'INSERT INTO {table_name} ({columns}) VALUES ({values})'
        cursor.execute(query_insert, list(data.values()))
        conn.commit()

        # Obtener el registro recién insertado
        query_select = f'SELECT * FROM {table_name} WHERE ID = ?'
        cursor.execute(query_select, cursor.execute('SELECT SCOPE_IDENTITY()').fetchval())
        inserted_row = cursor.fetchone()

        if inserted_row:
            inserted_record = {column[0]: value for column, value in zip(cursor.description, inserted_row)}
            return jsonify({'message': 'Registro creado exitosamente.', 'record': inserted_record})
        else:
            return jsonify({'error': 'No se pudo obtener el registro recién creado.'})

    except Exception as e:
        # Log de errores
        app.logger.error(f"Error al crear un nuevo registro: {str(e)}")
        return jsonify({'error': 'Error interno en el servidor.'}), 500

# Editar un registro en una tabla por ID
@app.route('/table/<string:table_name>/<int:record_id>', methods=['PUT'])
def edit_record(table_name, record_id):
    try:
        _, _, edit_permission, _ = validate_headers()

        if not edit_permission:
            return jsonify({'error': 'No tiene permisos de edición.'}), 403

        data = request.json

        # Validar y sanitizar las entradas
        if not all(isinstance(key, str) and isinstance(value, (str, int, float, bool)) for key, value in data.items()):
            return jsonify({'error': 'Datos no válidos.'}), 400

        set_clause = ', '.join([f'{column} = ?' for column in data.keys()])

        # Consulta parametrizada
        query = f'UPDATE {table_name} SET {set_clause} WHERE ID = ?'
        cursor.execute(query, list(data.values()) + [record_id])
        conn.commit()

        return jsonify({'message': f'Registro con ID {record_id} editado exitosamente.'})
    except Exception as e:
        # Log de errores
        app.logger.error(f"Error al editar un registro: {str(e)}")
        return jsonify({'error': 'Error interno en el servidor.'}), 500

# Eliminar un registro en una tabla por ID
@app.route('/table/<string:table_name>/<int:record_id>', methods=['DELETE'])
def delete_record(table_name, record_id):
    try:
        _, _, _, delete_permission = validate_headers()

        if not delete_permission:
            return jsonify({'error': 'No tiene permisos de eliminación.'}), 403

        # Consulta parametrizada
        query = f'DELETE FROM {table_name} WHERE ID = ?'
        cursor.execute(query, record_id)
        conn.commit()

        return jsonify({'message': f'Registro con ID {record_id} eliminado exitosamente.'})
    except Exception as e:
        # Log de errores
        app.logger.error(f"Error al eliminar un registro: {str(e)}")
        return jsonify({'error': 'Error interno en el servidor.'}), 500

# Filtrar registros en una tabla con el valor deseado
@app.route('/table/<string:table_name>/filter', methods=['POST'])
def filter_records(table_name):
    try:
        read_permission, _, _, _ = validate_headers()

        if not read_permission:
            return jsonify({'error': 'No tiene permisos de lectura.'}), 403

        filter_data = request.json

        # Validar y sanitizar las entradas
        if not all(isinstance(key, str) and isinstance(value, (str, int, float, bool)) for key, value in filter_data.items()):
            return jsonify({'error': 'Datos no válidos.'}), 400

        conditions = ' AND '.join([f'{column} = ?' for column, value in filter_data.items()])
        query = f'SELECT * FROM {table_name} WHERE {conditions}'
        cursor.execute(query, list(filter_data.values()))
        rows = cursor.fetchall()

        records = [{column[0]: value for column, value in zip(cursor.description, row)} for row in rows]
        return jsonify(records)
    except Exception as e:
        # Log de errores
        app.logger.error(f"Error al filtrar registros: {str(e)}")
        return jsonify({'error': 'Error interno en el servidor.'}), 500

if __name__ == '__main__':
    # Configuración para producción con Gunicorn y gevent
    app.config['PROPAGATE_EXCEPTIONS'] = True
    http_server = WSGIServer(('', 5000), app)
    http_server.serve_forever()

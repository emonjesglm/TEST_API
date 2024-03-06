# Usa una imagen base de Python oficial.
FROM python:3.9-slim

# Establece el directorio de trabajo en el contenedor
WORKDIR /app

# Instala dependencias del sistema para pyodbc
RUN apt-get update && apt-get install -y g++ unixodbc-dev

# Copia los archivos de requisitos y el código de la aplicación al contenedor
COPY requirements.txt ./
COPY . .

# Instala las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Expone el puerto que tu aplicación utiliza
EXPOSE 5000

# Comando para ejecutar tu aplicación
CMD ["python", "./app.py"]

# Create a ubuntu base image with python 3
FROM ubuntu:22.04

# Set the working directory
WORKDIR /stockcount

# Install the dependencies
COPY ./requirements.txt /stockcount/requirements.txt
COPY ./etc/config.json /etc/config.json
RUN apt update && apt install -y python3-pip libpq-dev
RUN pip3 install --no-cache-dir --upgrade -r requirements.txt

# Copy the app
COPY . /stockcount

# start the server
CMD ["uvicorn", "run:asgi_app", "--host", "0.0.0.0", "--port", "80", "--reload", "--reload-include *.json"]

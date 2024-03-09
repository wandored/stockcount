# Create a ubuntu base image with python 3
FROM ubuntu:22.04

# Set the working directory
WORKDIR /stockcount

# Install the dependencies
RUN apt-get -y update
RUN pip3 install -r ./stockcount/requirements.txt

# Copy the app
COPY . /stockcount

# start the server
CMD ["uvicorn", "run:asgi_app", "--host", "0.0.0.0", "--port", "80", "--reload", "--reload-include *.json"]

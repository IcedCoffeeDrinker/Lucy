FROM python:3.12-slim

WORKDIR /app

# Copy and install requirements
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY ./src /app/src

# Expose the port the app runs on
EXPOSE 5001

# Command to run the application
CMD ["uvicorn", "src.services.main:app", "--host", "0.0.0.0", "--port", "5001"] 

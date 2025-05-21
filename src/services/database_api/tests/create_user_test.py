import httpx

url = "http://localhost:5001/database_api/create_user"

name = input("Enter a name > ")
phone_number = input("Enter a phone number > ")
data = {"name": name, "phone_number": phone_number}
response = httpx.post(url, json=data)
print(response.json())
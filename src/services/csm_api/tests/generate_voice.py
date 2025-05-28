import httpx

url = "http://localhost:5001/csm_api/conversation"

user_id = "test"
user_text = ""
llm_text = "Hello, how are you?"
data = {"user_text": user_text, "llm_text": llm_text}
response = httpx.post(url+f"/{user_id}", json=data)
print(response.json())
response = httpx.post(url+f"/terminate/{user_id}")
print(response.json())
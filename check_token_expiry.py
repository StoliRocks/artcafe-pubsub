import json
import base64
from datetime import datetime

token = "eyJraWQiOiIxWUxrNHdCV2x5YU52U1FhTzBET1VQemZlYnQ3U05oTHFGQ1wvbWVHbE5DVT0iLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJmNDU4NTRkOC0yMGExLTcwYjgtYTYwOC0wZDhiZmQ1ZjJjZmMiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiaXNzIjoiaHR0cHM6XC9cL2NvZ25pdG8taWRwLnVzLWVhc3QtMS5hbWF6b25hd3MuY29tXC91cy1lYXN0LTFfWVVNUVMzTzJKIiwiY29nbml0bzp1c2VybmFtZSI6InN0dndoaXRlQHlhaG9vLmNvbSIsImdpdmVuX25hbWUiOiJTdGV2ZW4iLCJvcmlnaW5fanRpIjoiZjA1ZTM4OTAtZDJlYS00NmU2LWJlZmMtODA0MWNjNGNkZTQ1IiwiYXVkIjoiMzRzcmlsdWJhb3UzdTFodTYyNnRtaW9vZGkiLCJldmVudF9pZCI6IjRlYzg1ZThiLTkxOWYtNDAzYS1iNTE0LWQ0YzFmYzkxNjY2YSIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNzQ4ODk1MDkyLCJuYW1lIjoiU3RldmVuIFdoaXRlIiwiZXhwIjoxNzQ4OTgyNzc0LCJpYXQiOjE3NDg5NzkxNzQsImZhbWlseV9uYW1lIjoiV2hpdGUiLCJqdGkiOiI4ZGNjOTUyNi1lOTFlLTQ1MTEtODViMS1lM2Q5YjNlNGQwY2EiLCJlbWFpbCI6InN0dndoaXRlQHlhaG9vLmNvbSJ9.SHdAFR7KdSxkk_2I698tM0dZ3PPJXnHmEsCkHsgAEs2KBnzsZthYLdLMrbO1pKtwt6Q9aGFCW7Hypu8XcBYbdN6mn1_MFL3eu8JAI03omBVu9jEREvgy_0twdRDdLnvPmwkQk40CABatcbZe0BZC-Qa93y-3ELiiBq8EiJK6UPm1um9GBU3056eKKiVNgiU_OzjzoJY61KbVLSOZpfVZ10PAh6TOmwGMAXNUOj6-QC7nrOqO0mX42cIfXFX17w5WNduI0zfDef94xuq4OTg_2hrbafsaDKxqtlFenORz8D4W_3cJFFvjebohvMj5LiUHpt_dEqDh-GZYk5mHz7zGjA"

# Split the token
parts = token.split('.')
payload = parts[1]

# Add padding if needed
padding = 4 - len(payload) % 4
if padding:
    payload += '=' * padding

# Decode
decoded = base64.b64decode(payload)
data = json.loads(decoded)

# Check expiration
exp = data.get('exp')
exp_datetime = datetime.fromtimestamp(exp)
now = datetime.now()

print(f"Token expires at: {exp_datetime}")
print(f"Current time: {now}")
print(f"Expired: {now > exp_datetime}")
print(f"Time until expiry: {exp_datetime - now}")

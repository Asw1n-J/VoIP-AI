import os
import random
import requests
from dotenv import load_dotenv
from supabase import create_client, Client
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware


load_dotenv()

SUPABASE_URL = os.getenv("supabase_url")
SUPABASE_KEY = os.getenv("supabase_key")
EMAILJS_SERVICE_ID = os.getenv("emailjs_service_id")
EMAILJS_TEMPLATE_ID = os.getenv("emailjs_template_id")
EMAILJS_PUBLIC_KEY = os.getenv("emailjs_public_key")

AC_NUM = None


if not SUPABASE_KEY or not SUPABASE_URL:
    raise ValueError("No valid credentials for the DB")

supabase: Client = create_client(SUPABASE_URL,SUPABASE_KEY)

app = FastAPI(title="VoIP AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def send_email_otp(to_email:str, pin:str):
    url = "https://api.emailjs.com/api/v1.0/email/send"

    payload = {
        "service_id": EMAILJS_SERVICE_ID,
        "template_id": EMAILJS_TEMPLATE_ID,
        "user_id": EMAILJS_PUBLIC_KEY,
        "template_params": {
            "to_email": to_email,
            "pin": pin,
            "message": f"{pin} is your Forex Security Code",
            "name": "XYZ Forex"
        }
    }

    response = requests.post(url, json=payload)
    
    if response.status_code != 200:
        raise Exception(f"EmailJS Error ({response.status_code}): {response.text}")



class generateOTP(BaseModel):
    account_number: str

class verifyOTP(BaseModel):
    account_number:str
    pin: str

@app.get("/")
def home():
    return {"status":"online", "message":"Forex DB is healthy"}


@app.post("/otp")
async def trigger_otp(request: Request):
    global AC_NUM

    data = await request.json()

    # Extract account_number across flat JSON, query args, or Vapi's nested message wrapper
    account_number = (
        data.get("account_number")
        or data.get("accountNumber")
        or data.get("args", {}).get("account_number")
    )

    # If it came directly from a Vapi Server URL Webhook:
    if not account_number and "message" in data:
        message = data.get("message", {})
        tool_calls = message.get("toolCalls") or message.get("toolWithToolCallList") or []
        if tool_calls:
            # Handle standard Vapi tool call or toolWithToolCallList wrapper
            first_call = tool_calls[0]
            func_args = (
                first_call.get("function", {}).get("arguments")
                or first_call.get("toolCall", {}).get("function", {}).get("arguments")
                or {}
            )
            account_number = func_args.get("account_number") or func_args.get("accountNumber")

    if not account_number:
        raise HTTPException(
            status_code=422,
            detail="Missing 'account_number' in request payload."
        )

    clean_account = "".join(filter(str.isdigit, str(account_number)))

    res = (
        supabase.table("forexdata")
        .select("*")
        .eq("account_number", clean_account)
        .execute()
    )

    if not res.data:
        return {
            "success": False,
            "status": "error",
            "detail": "account_not_found",
            "message": f"Account number {clean_account} was not found."
        }

    AC_NUM = clean_account
    user_email = "ddtestop@yopmail.com"
    pin = str(random.randint(1000, 9999))

    supabase.table("forexdata").update({"pin": pin}).eq("account_number", clean_account).execute()

    try:
        send_email_otp(user_email, pin)
        return {
            "success": True,
            "status": "success",
            "detail": "OTP sent",
            "account_number": clean_account,
            "email": user_email,
            "message": "OTP sent and DB updated"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@app.post("/verify-otp")
def verify_otp(payload: verifyOTP):

    global AC_NUM

    res=(
        supabase.table("forexdata")
        .select("*")
        .eq("account_number", AC_NUM)
        .eq("pin", payload.pin)
        .execute()
    )

    if not res.data:
        return{
            "status":"falied",
            "detail":"access denied",
            "message": "The pin doesnt match",
        }

    record = res.data[0]

    return{
        "detail":"access granted",
        "message":"OTP verified successfully",
        "status": record.get("status"),
        "issue": record.get("issue")
    }
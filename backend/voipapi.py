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
    mobile: str

class verifyOTP(BaseModel):
    account_number:str
    mobile: str
    pin: str

@app.get("/")
def home():
    return {"status":"online", "message":"Forex DB is healthy"}


@app.post("/otp")
def trigger_otp(payload: generateOTP):

    res = (
        supabase.table("forexdata")
        .select("*")
        .eq("account_number", payload.account_number)
        .eq("mobile", payload.mobile)
        .execute()
    )

    if not res.data:
        raise HTTPException(
            status_code=404,
            detail = f"The credentials are invalid",
        )

    user_email = "ddtestop@yopmail.com"
    pin = str(random.randint(1000,9999))

    supabase.table("forexdata").update({"pin":pin}).eq("account_number",payload.account_number).eq("mobile", payload.mobile).execute()

    try:
        send_email_otp(user_email, pin)
        return{
            "status":"sent",
            "account_number":payload.account_number,
            "mobile": payload.mobile,
            "email":user_email,
            "pin": pin,
            "message": "OTP sent and DB updated"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail = f"Failed to send email: {str(e)}")


@app.post("/verify-otp")
def verify_otp(payload: verifyOTP):

    res=(
        supabase.table("forexdata")
        .select("*")
        .eq("account_number", payload.account_number)
        .eq("mobile", payload.mobile)
        .eq("pin", payload.pin)
        .execute()
    )

    if not res.data:
        return{
            "status":"falied",
            "access":"denied",
            "message": "The pin doesnt match",
        }

    return{
        "status":"success",
        "access":"granted",
        "message":"OTP verified successfully"
    }
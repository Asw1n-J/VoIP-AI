import os
import random
from dotenv import load_dotenv
from supabase import create_client, Client
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel


load_dotenv()

SUPABASE_URL = os.getenv("supabase_url")
SUPABASE_KEY = os.getenv("supabase_key")
GMAIL_USER = os.getenv("gmail_address")
GMAIL_PASSWORD = os.getenv("gmail_app_password")


if not SUPABASE_KEY or not SUPABASE_URL:
    raise ValueError("No valid credentials for the DB")

supabase: Client = create_client(SUPABASE_URL,SUPABASE_KEY)

app = FastAPI(title="VoIP AI Backend")

def send_email_otp(to_email:str, pin:str):
    msg = MIMEMultipart()
    msg["From"] = f"Forex OTP for verification"
    msg["To"] = to_email
    msg["Subject"] = f"{pin} is your Forex Security Code"

    body = (
        f"Hello,\nYour 4 digit forex security code is {pin}"
    )
    msg.attach(MIMEText(body,"plain"))

    with smtplib.SMTP("smtp.gmail.com",587) as server:
        server.starttls()
        server.login(GMAIL_USER,GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, to_email, msg.as_string())



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
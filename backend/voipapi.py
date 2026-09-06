import os
import random
import requests
from dotenv import load_dotenv
from supabase import create_client, Client
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

SUPABASE_URL = os.getenv("supabase_url")
SUPABASE_KEY = os.getenv("supabase_key")
EMAILJS_SERVICE_ID = os.getenv("emailjs_service_id")
EMAILJS_TEMPLATE_ID = os.getenv("emailjs_template_id")
EMAILJS_PUBLIC_KEY = os.getenv("emailjs_public_key")

if not SUPABASE_KEY or not SUPABASE_URL:
    raise ValueError("No valid credentials for the DB")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="VoIP AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def send_email_otp(to_email: str, pin: str):
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
    response = requests.post(url, json=payload, timeout=5)
    if response.status_code != 200:
        raise Exception(f"EmailJS Error ({response.status_code}): {response.text}")

def parse_vapi_or_flat_payload(data: dict):
    """
    Extracts tool call ID, function arguments, and detects whether
    the request came as a Vapi Server Webhook or a flat JSON payload.
    """
    tool_call_id = None
    args = {}
    is_vapi_webhook = False

    if "message" in data:
        is_vapi_webhook = True
        message = data.get("message", {})
        tool_calls = message.get("toolCalls") or message.get("toolWithToolCallList") or []
        if tool_calls:
            first_call = tool_calls[0]
            tool_call_id = first_call.get("id") or first_call.get("toolCall", {}).get("id")
            args = (
                first_call.get("function", {}).get("arguments")
                or first_call.get("toolCall", {}).get("function", {}).get("arguments")
                or {}
            )
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
    else:
        args = data

    return args, tool_call_id, is_vapi_webhook

def format_vapi_response(result_text: str, tool_call_id: str, is_webhook: bool):
    """
    Formats the response so Vapi receives the exact payload schema it requires.
    """
    if is_webhook and tool_call_id:
        return {
            "results": [
                {
                    "toolCallId": tool_call_id,
                    "result": result_text
                }
            ]
        }
    return {
        "success": True,
        "result": result_text
    }

@app.get("/")
def home():
    return {"status": "online", "message": "Forex DB is healthy"}

@app.post("/otp")
async def trigger_otp(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    args, tool_call_id, is_webhook = parse_vapi_or_flat_payload(data)

    raw_account = (
        args.get("account_number") 
        or args.get("accountNumber") 
        or args.get("account")
    )

    if not raw_account:
        return format_vapi_response(
            "No account number was provided. Ask the user to state their account number clearly.",
            tool_call_id,
            is_webhook
        )

    clean_account = "".join(filter(str.isdigit, str(raw_account)))

    try:
        res = supabase.table("forexdata").select("*").eq("account_number", clean_account).execute()
    except Exception as e:
        return format_vapi_response(f"Database error: {str(e)}", tool_call_id, is_webhook)

    if not res.data:
        return format_vapi_response(
            f"Account number {clean_account} was not found in our database. Ask the user to double check their account number.",
            tool_call_id,
            is_webhook
        )

    user_email = "ddtestop@yopmail.com"
    pin = str(random.randint(1000, 9999))

    try:
        supabase.table("forexdata").update({"pin": pin}).eq("account_number", clean_account).execute()
        send_email_otp(user_email, pin)
    except Exception as e:
        return format_vapi_response(
            f"Account {clean_account} found, but sending the security email failed: {str(e)}",
            tool_call_id,
            is_webhook
        )

    return format_vapi_response(
        f"Account number {clean_account} has been verified and an OTP security code was emailed to the user. Ask the user to provide the 4-digit security code.",
        tool_call_id,
        is_webhook
    )

@app.post("/verify-otp")
async def verify_otp(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    args, tool_call_id, is_webhook = parse_vapi_or_flat_payload(data)

    raw_pin = args.get("pin") or args.get("otp") or args.get("code")
    raw_account = args.get("account_number") or args.get("accountNumber")

    if not raw_pin:
        return format_vapi_response(
            "PIN code was not provided. Ask the user for their 4-digit OTP code.",
            tool_call_id,
            is_webhook
        )

    clean_pin = "".join(filter(str.isdigit, str(raw_pin)))
    clean_account = "".join(filter(str.isdigit, str(raw_account))) if raw_account else None

    # Query DB with account_number if available, otherwise search strictly by PIN
    query = supabase.table("forexdata").select("*").eq("pin", clean_pin)
    if clean_account:
        query = query.eq("account_number", clean_account)

    try:
        res = query.execute()
    except Exception as e:
        return format_vapi_response(f"Database verification error: {str(e)}", tool_call_id, is_webhook)

    if not res.data:
        return format_vapi_response(
            "Access denied. The PIN provided is incorrect. Please ask the user to re-enter their PIN.",
            tool_call_id,
            is_webhook
        )

    record = res.data[0]
    account_status = record.get("status", "Active")
    issue = record.get("issue", "None")

    return format_vapi_response(
        f"Access granted! OTP verified successfully. Account Status: {account_status}. Account Issue: {issue}.",
        tool_call_id,
        is_webhook
    )
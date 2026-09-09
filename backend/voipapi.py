import os
import json
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
    tool_call_id = None
    args = {}
    is_vapi_webhook = "message" in data or "toolCalls" in data

    if "message" in data:
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
    elif "toolCalls" in data:
        tool_calls = data.get("toolCalls", [])
        if tool_calls:
            first_call = tool_calls[0]
            tool_call_id = first_call.get("id")
            args = first_call.get("function", {}).get("arguments", {})
    else:
        args = data

    # Parse JSON string arguments if Vapi sends raw JSON string
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}

    return args, tool_call_id, is_vapi_webhook

def format_vapi_response(result_text: str, tool_call_id: str, is_webhook: bool):
    if is_webhook:
        return {
            "results": [
                {
                    "toolCallId": tool_call_id or "call_default",
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
        or args.get("account_no")
    )

    if not raw_account:
        return format_vapi_response(
            "No account number was provided. Please ask the user to state their account number clearly.",
            tool_call_id,
            is_webhook
        )

    clean_account = "".join(filter(str.isdigit, str(raw_account)))

    if not clean_account:
        return format_vapi_response(
            "Invalid account number structure. Ask the user to state only the numerical digits of their account.",
            tool_call_id,
            is_webhook
        )

    try:
        res = supabase.table("forexdata").select("*").eq("account_number", clean_account).execute()
    except Exception as e:
        return format_vapi_response(f"Database error: {str(e)}", tool_call_id, is_webhook)

    if not res.data:
        return format_vapi_response(
            f"Account number {clean_account} was not found in our records. Please ask the user to double check their account number.",
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
            f"Account {clean_account} located, but emailing the security code failed: {str(e)}",
            tool_call_id,
            is_webhook
        )

    return format_vapi_response(
        f"SUCCESS: Account {clean_account} verified and a 4-digit security code was emailed to the user. Ask the user to state the 4-digit security code they received.",
        tool_call_id,
        is_webhook
    )

@app.post("/verify-otp")
async def verify_otp(request: Request):
    body = await request.body()
    if not body:
        data = {}
    else:
        try:
            data = await request.json()
        except Exception:
            data = {}

    args, tool_call_id, is_webhook = parse_vapi_or_flat_payload(data)

    raw_pin = (
        args.get("pin") 
        or args.get("otp") 
        or args.get("code") 
        or args.get("otp_code")
    )
    raw_account = (
        args.get("account_number") 
        or args.get("accountNumber")
        or args.get("account")
    )

    clean_pin = "".join(filter(str.isdigit, str(raw_pin))) if raw_pin else ""
    clean_account = "".join(filter(str.isdigit, str(raw_account))) if raw_account else None
    
    if len(clean_pin) < 4:
        return format_vapi_response(
            "Waiting for the user to finish speaking all 4 digits of their security code. Do NOT say the code is incorrect yet.",
            tool_call_id,
            is_webhook
        )

    query = supabase.table("forexdata").select("*").eq("pin", clean_pin)
    if clean_account:
        query = query.eq("account_number", clean_account)

    try:
        res = query.execute()
    except Exception as e:
        return format_vapi_response(f"Database verification error: {str(e)}", tool_call_id, is_webhook)

    if not res.data:
        return format_vapi_response(
            "Access denied: The security PIN provided is incorrect. Please ask the user to re-check their email and state the 4-digit code again.",
            tool_call_id,
            is_webhook
        )

    record = res.data[0]
    account_status = record.get("status", "Active")
    issue = record.get("issue", "None")

    return format_vapi_response(
        f"SUCCESS: OTP verified and access granted! Account Status: {account_status}. Issue details: {issue}. Do NOT ask for the PIN again.",
        tool_call_id,
        is_webhook
    )

@app.post("/exchange-rate")
async def get_exchange_rate(request: Request):
    body = await request.body()
    if not body:
        data = {}
    else:
        try:
            data = await request.json()
        except Exception:
            data = {}

    args, tool_call_id, is_webhook = parse_vapi_or_flat_payload(data)

    from_curr = str(args.get("from_currency") or args.get("from") or "USD").upper().strip()
    to_curr = str(args.get("to_currency") or args.get("to") or "EUR").upper().strip()
    
    raw_amount = args.get("amount") or 1.0
    try:
        amount = float(raw_amount)
    except (ValueError, TypeError):
        amount = 1.0

    try:
        url = f"https://open.er-api.com/v6/latest/{from_curr}"
        response = requests.get(url, timeout=5)

        if response.status_code == 200 and response.text.strip():
            api_data = response.json()
            rates = api_data.get("rates", {})
        else:
            rates = {}

        if to_curr not in rates:
            return format_vapi_response(
                f"Currency code {to_curr} is not supported. Please ask the user to provide standard codes like USD, EUR, or GBP.",
                tool_call_id,
                is_webhook
            )

        unit_rate = round(rates[to_curr], 4)
        converted_total = round(amount * unit_rate, 2)

        return format_vapi_response(
            f"The current exchange rate from {from_curr} to {to_curr} is {unit_rate}. {amount} {from_curr} equals {converted_total} {to_curr}.",
            tool_call_id,
            is_webhook
        )

    except Exception as e:
        return format_vapi_response(
            f"Unable to retrieve live exchange rates at the moment due to an external network error: {str(e)}",
            tool_call_id,
            is_webhook
        )
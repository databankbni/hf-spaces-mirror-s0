print("A")
import asyncio

from download_assets import download_assets
print("A")
from fastapi.middleware.cors import CORSMiddleware
print("A")
from models import ComplaintCreate, ComplaintUpdate, UserLogin
print("A")
from fastapi import (
    FastAPI,
    HTTPException,
    Body,
    UploadFile,
    File,
    Header,
    Response,
)
print("A")
from services import (
    register_complaint,
    get_all_complaints,
    update_complaint_status,
    get_ai_engine,
    get_rca_engine,
    login_user,
    get_user_from_session
)
print("A")
from database import get_db_status
print("A")
from typing import List, Optional
print("A")
import os
print("A")
import io
print("A")
import fitz
print("A")
import uuid
print("A")
from dotenv import load_dotenv
print("A")
from nba.incremental_embeddings import add_document_incrementally
print("A")
from logger import get_logger
print("A")


load_dotenv()

app = FastAPI(title="Smart Resolve Bot API")

# Initialize logging system
log_system = get_logger()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://customercomplaintdashboard.vercel.app",
        "https://uni1-0-black.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8081",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_sessions = {}


@app.get("/")
async def root():
    return {"message": "Welcome to Smart Resolve Bot API"}

@app.post("/auth/login", response_model=dict)
async def login(
    credentials: UserLogin,
):
    try:
        user, session_id = await login_user(credentials)
 
        return {
            "success": True,
            "user": user,
            "session_id": session_id,
        }
 
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

from fastapi import Header

@app.get("/auth/me")
async def get_current_user(
    authorization: str | None = Header(default=None)
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_id = authorization.replace("Bearer ", "")

    try:
        user = await get_user_from_session(session_id)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=503, detail=f"Session lookup failed: {e}")

    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return user


@app.post("/complaints/", response_model=dict)
async def create_complaint(
    complaint: ComplaintCreate,
    authorization: str | None = Header(default=None)
):
    try:
        if authorization:
            session_id = authorization.replace("Bearer ", "")
            user = await get_user_from_session(session_id)
            if user and user.get("role") == "customer":
                complaint.customer_id = user.get("customer_id", complaint.customer_id)
                complaint.customer_name = user.get("customer_name", complaint.customer_name)
                complaint.branch_id = user.get("branch_id", complaint.branch_id)
                complaint.state = user.get("state", complaint.state)
                complaint.zip_code = user.get("zip_code", complaint.zip_code)
        new_complaint = await register_complaint(complaint)
        return new_complaint
    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        print(f"ERROR in create_complaint: {error_details}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "type": type(e).__name__,
                "message": "The server encountered an error while registering the complaint. This is likely a database connection issue or an AI engine timeout.",
            },
        )


@app.post("/channels/pdf-extract")
async def extract_pdf_text(file: UploadFile = File(...)):
    try:
        content = await file.read()

        doc = fitz.open(
            stream=content,
            filetype="pdf"
        )

        text = ""

        for page in doc:
            text += page.get_text("text")

        doc.close()

        if not text.strip():
            return {
                "text": "No text could be extracted from this PDF."
            }

        return {
            "text": text.strip()
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF extraction failed: {str(e)}"
        )


@app.post(
    "/channels/ocr",
)
async def handle_ocr(
    file: UploadFile = File(...),
    customer_id: str = Body(...),
    customer_name: str = Body(...),
):
    text_content = f"Extracted text from {file.filename}: I have a problem with my credit card billing."
    complaint = ComplaintCreate(
        customer_id=customer_id,
        customer_name=customer_name,
        product="Credit Card",
        issue="Billing Error",
        consumer_complaint_narrative=text_content,
        submitted_via="OCR",
    )
    return await register_complaint(complaint)


@app.post("/channels/voice")
async def handle_voice(
    customer_id: str = Body(...),
    customer_name: str = Body(...),
    voice_text: str = Body(...),
):
    complaint = ComplaintCreate(
        customer_id=customer_id,
        customer_name=customer_name,
        product="General",
        issue="Voice Complaint",
        consumer_complaint_narrative=voice_text,
        submitted_via="Voice",
    )
    return await register_complaint(complaint)


@app.get("/complaints/", response_model=List[dict])
async def list_complaints():
    try:
        return await get_all_complaints()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chatbot/chat")
async def chatbot_chat(payload: dict = Body(...)):
    
    message = payload.get("message")
    session_id = payload.get("session_id")
    history = payload.get("history", [])
    existing_fields = payload.get("existing_fields", {})

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    if not session_id:
        session_id = str(uuid.uuid4())
        chat_sessions[session_id] = {
            "fields": {
                "customer_name": "",
                "customer_id": "",
                "product": "",
                "issue": "",
                "narrative": "",
            },
            "history": [],
        }

    session = chat_sessions.get(
        session_id,
        {
            "fields": {
                "customer_name": "",
                "customer_id": "",
                "product": "",
                "issue": "",
                "narrative": "",
            },
            "history": [],
        },
    )

    merged_fields = {**session["fields"], **existing_fields}
    ai_engine = await get_ai_engine()

    ai_response = await ai_engine.get_chatbot_response(
        message=message,
        history=history,
        existing_fields=merged_fields,
        session_id=session_id,
    )

    session["fields"] = ai_response["metadata"]["fields"]
    session["history"].append({"role": "user", "content": message})
    session["history"].append({"role": "assistant", "content": ai_response["answer"]})
    chat_sessions[session_id] = session

    metadata = ai_response["metadata"]
    registered_complaint = None

    if metadata.get("status") == "REGISTERED":
        fields = metadata["fields"]
        try:
            narrative = fields.get("narrative", message) or message

            amount_str = str(fields.get("amount", "0")).replace("$", "").replace(",", "")
            try:
                financial_amount = float(amount_str)
            except Exception:
                financial_amount = 0.0

            complaint_data = ComplaintCreate(
                customer_id=fields.get("customer_id", f"CHAT-{uuid.uuid4().hex[:8]}"),

                customer_name=fields.get("customer_name", "Unknown Customer"),
                product=fields.get("product", "General"),
                sub_product=fields.get("sub_product"),
                issue=fields.get("issue", "General Inquiry"),
                sub_issue=fields.get("sub_issue"),
                consumer_complaint_narrative=narrative,
                submitted_via="Chatbot",
                financial_impact_amount=financial_amount,
            )

            registered_complaint = await register_complaint(complaint_data)
            ai_response["answer"] = f"{registered_complaint['ai_generated_response']}"
        except Exception as e:
            import traceback

            print(traceback.format_exc())
            ai_response["answer"] += f"\n\n(Error during registration: {str(e)})"

    return {
        "response": ai_response["answer"],
        "metadata": {**metadata, "session_id": session_id, "registered_complaint": registered_complaint},
    }


@app.patch("/complaints/{complaint_id}")
async def update_status(complaint_id: str, update: ComplaintUpdate):
    try:
        updated = await update_complaint_status(
            complaint_id,
            update.status,
            update.company_response_to_consumer,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return updated
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/root-cause/{product:path}")
async def get_root_cause(product: str):
    try:
        # Normalize spacing/encoding issues from frontend route params.
        product = product.replace("%2F", "/").replace("%20", " ").strip()

        complaints = await get_all_complaints()
        product_complaints = [
            c["consumer_complaint_narrative"]
            for c in complaints
            if c.get("product") == product
        ]

        if not product_complaints:
            return {
                "current_issues": "No data available for this product.",
                "recommendation": "No data available for this product."
            }

        ai_engine = await get_ai_engine()
        root_cause = await ai_engine.identify_root_cause(
            product_complaints,
            product,
        )
        return root_cause
    except Exception as e:
        return {
            "current_issues": f"Error: {str(e)}",
            "recommendation": f"Error: {str(e)}"
        }



@app.get("/system/db-status")
async def db_status():
    return await get_db_status()


@app.post("/logs/frontend-event")
async def log_frontend_event(event_data: dict = Body(...)):
    """Log frontend user interactions"""
    try:
        session_id = event_data.get("session_id", "UNKNOWN")
        customer_id = event_data.get("customer_id", "UNKNOWN")
        page = event_data.get("page", "UNKNOWN")
        event = event_data.get("event", "UNKNOWN")
        details = event_data.get("details")
        
        log_system.log_frontend_event(
            session_id=session_id,
            customer_id=customer_id,
            page=page,
            event=event,
            details=details
        )
        
        return {"success": True}
    except Exception as e:
        # Never fail the frontend due to logging errors
        return {"success": False, "error": str(e)}


@app.on_event("startup")
async def startup_event():
    print("Startup: begin", flush=True)

    print("Downloading assets...", flush=True)
    download_assets()
    print("Assets done", flush=True)

    print("Loading AI...", flush=True)
    await get_ai_engine()
    print("AI done", flush=True)

    print("Loading RAG...", flush=True)
    await get_rca_engine()
    print("RAG done", flush=True)

    print("Startup finished", flush=True)
    
    # Optional: Run email ingest AFTER startup, in the background — never
    # block Uvicorn's readiness on this. It uses blocking poplib/smtplib
    # calls and can process up to EMAIL_INGEST_MAX emails through the full
    # AI pipeline, which can take minutes. Awaiting it here delays every
    # cold start by that same amount.
    run_flag = os.getenv("RUN_EMAIL_INGEST_ON_STARTUP", "false").lower()
    if run_flag in ("1", "true", "yes", "y"):
        asyncio.create_task(_run_email_ingest_background())

    print("🎉 Application setup complete!")

async def _run_email_ingest_background():
    import asyncio as _asyncio

    print("📧 Running email ingest in background...", flush=True)
    try:
        from admin_email_ingest_job import ingest_and_reply

        max_messages = int(os.getenv("EMAIL_INGEST_MAX", "10"))
        # poplib/smtplib are synchronous — run them off the event loop so
        # they don't block request handling while ingest is in progress.
        await _asyncio.to_thread(
            lambda: _asyncio.run(ingest_and_reply(max_messages=max_messages))
        )
        print("📧 Email ingest finished.", flush=True)
    except Exception as e:
        print(f"Email ingest failed: {e}", flush=True)


@app.post("/channels/email", response_model=dict)
async def ingest_email_channel(
    customer_id: str = Body(...),
    customer_name: str = Body(...),
    email_subject: str = Body(""),
    email_body: str = Body(...),
):
    from channels_email import ingest_email_to_complaint

    return await ingest_email_to_complaint(
        customer_id=customer_id,
        customer_name=customer_name,
        email_subject=email_subject,
        email_body=email_body,
    )


@app.post("/nba/upload-document")
async def upload_nba_document(file: UploadFile = File(...)):
    try:
        # Validate file type
        if not file.filename.endswith(".docx"):
            raise HTTPException(status_code=400, detail="Only .docx files are supported for NBA knowledge base")

        # Save the file to nba/documents
        os.makedirs("nba/documents", exist_ok=True)
        file_path = os.path.join("nba/documents", file.filename)
        
        # Check if file already exists
        if os.path.exists(file_path):
            raise HTTPException(status_code=409, detail="File already exists in knowledge base")
        
        with open(file_path, "wb") as f:
            f.write(await file.read())

        # Add to FAISS index incrementally
        result = add_document_incrementally(file_path, file.filename)
        
        return {
            "success": True,
            "message": "Document uploaded and embeddings added successfully",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error uploading document: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@app.get("/nba/documents")
async def list_nba_documents():
    try:
        os.makedirs("nba/documents", exist_ok=True)
        files = [f for f in os.listdir("nba/documents") if f.endswith(".docx")]
        return {
            "success": True,
            "documents": files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@app.delete("/nba/documents/{filename}")
async def delete_nba_document(filename: str):
    try:
        from nba.incremental_embeddings import delete_document
        result = delete_document(filename)
        return {
            "success": True,
            "message": f"Document {filename} deleted successfully",
            "data": result
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document {filename} not found")
    except Exception as e:
        import traceback
        print(f"Error deleting document: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


import os
import smtplib
from email.mime.text import MIMEText
from google.adk.agents import Agent
from google.adk.tools import google_search  # Import the tool
from google.adk.tools.function_tool import FunctionTool

def send_gmail(subject: str, body: str) -> str:
    """Sends an email via Gmail to x@gmail.com.
    
    Args:
        subject: Email subject.
        body: Email body content.
    """
    sender = os.environ.get("GMAIL_SENDER")
    password = os.environ.get("GMAIL_PASSWORD")
    to = "x@gmail.com"
    
    if not sender or not password:
        return "Error: GMAIL_SENDER and GMAIL_PASSWORD environment variables not set."
        
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, [to], msg.as_string())
        return f"Email sent successfully to {to}!"
    except Exception as e:
        return f"Failed to send email: {e}"

gmail_tool = FunctionTool(send_gmail)

root_agent = Agent(
   name="ai_glasses_agent",
   model="gemini-live-2.5-flash-native-audio",
   description="Agent for AI glasses, supporting audio, video, Google Search, and Gmail.",
   instruction="""You are an agentic AI glasses assistant. You interact with the user in real-time via audio and video.
Follow these rules strictly:
1. Persona: You are an intelligent pair of AI glasses. You assist the user by describing what you see and answering questions.
2. Interaction: Wait for the user's audio input before answering. Do not start speaking proactively unless the user asks you to describe something or asks a question.
3. Focus: Only answer questions the user has explicitly asked. Do not provide unsolicited information or continue talking beyond answering the question.
4. Interruption: If the user says "stop", you must immediately stop your current response.
5. Vision: Describe what you see in the video feed whenever the user asks or when relevant to answer their questions.
6. Tools: You can use the Google Search tool to find real-time information and the Gmail tool to send emails to shashvik@gmail.com when requested by the user.""",
   tools=[google_search, gmail_tool]
)

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from app.core.config import settings
from app.utils.logger import logger

class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_pass = settings.SMTP_PASS
        self.smtp_from = settings.SMTP_FROM
        
        logger.info(f"Email service initialized with Brevo SMTP: {self.smtp_host}:{self.smtp_port}")

    def _validate_configuration(self) -> bool:
        """Validate Brevo SMTP configuration"""
        required_fields = [self.smtp_host, self.smtp_user, self.smtp_pass, self.smtp_from]
        
        if not all(required_fields):
            missing = [field for field, value in zip(
                ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASS', 'SMTP_FROM'],
                required_fields
            ) if not value]
            
            logger.error(f"Email configuration incomplete. Missing: {', '.join(missing)}")
            return False
            
        # Validate Brevo-specific configuration
        if 'brevo.com' not in self.smtp_host:
            logger.warning(f"SMTP_HOST ({self.smtp_host}) doesn't appear to be Brevo. Brevo uses smtp-relay.brevo.com")
        
        return True

    # def send_email(self, to_email: str, subject: str, html_content: str, text_content: str = None) -> bool:
    #     """Send an email using Brevo SMTP"""
    #     if not self._validate_configuration():
    #         logger.error("Brevo SMTP configuration validation failed")
    #         return False
        
    #     if not text_content:
    #         # Create basic plain text version from HTML
    #         import re
    #         text_content = re.sub(r'<[^>]*>', '', html_content)
    #         text_content = re.sub(r'\s+', ' ', text_content).strip()

    #     # Create message
    #     msg = MIMEMultipart("alternative")
    #     msg["Subject"] = subject
    #     msg["From"] = formataddr(("PaperBrain", self.smtp_from))
    #     msg["To"] = to_email
        
    #     # Add headers for better deliverability
    #     msg["X-Mailer"] = "PaperBrain/1.0"
    #     msg["X-Accept-Language"] = "en"
        
    #     # Attach both plain text and HTML versions
    #     msg.attach(MIMEText(text_content, "plain"))
    #     msg.attach(MIMEText(html_content, "html"))
        
    #     try:
    #         # Connect to Brevo SMTP server
    #         logger.info(f"Connecting to Brevo SMTP: {self.smtp_host}:{self.smtp_port}")
            
    #         with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
    #             # Debug information
    #             logger.debug(f"SMTP server: {self.smtp_host}:{self.smtp_port}")
    #             logger.debug(f"SMTP user: {self.smtp_user}")
                
    #             # Identify ourselves
    #             server.ehlo()
                
    #             # Start TLS encryption (required for Brevo)
    #             if server.has_extn('STARTTLS'):
    #                 server.starttls()
    #                 server.ehlo()  # Re-identify after TLS
    #                 logger.debug("TLS encryption started")
                
    #             # Login to Brevo SMTP
    #             logger.debug("Authenticating with Brevo SMTP...")
    #             server.login(self.smtp_user, self.smtp_pass)
    #             logger.debug("SMTP authentication successful")
                
    #             # Send email
    #             logger.info(f"Sending email to: {to_email}")
    #             server.sendmail(self.smtp_from, to_email, msg.as_string())
    #             logger.debug("Email sent successfully")
                
    #         logger.info(f"Email sent successfully to {to_email}")
    #         return True
            
    #     except smtplib.SMTPAuthenticationError as e:
    #         logger.error(f"Brevo SMTP authentication failed: {e}")
    #         logger.error("Please check:")
    #         logger.error("- SMTP_USER is your Brevo login email (not from address)")
    #         logger.error("- SMTP_PASS is your Brevo SMTP key (not account password)")
    #         logger.error("- SMTP key has SMTP permissions in Brevo dashboard")
    #         return False
            
    #     except smtplib.SMTPConnectError as e:
    #         logger.error(f"Cannot connect to Brevo SMTP server: {e}")
    #         logger.error("Please check:")
    #         logger.error("- SMTP_HOST is 'smtp-relay.brevo.com'")
    #         logger.error("- SMTP_PORT is 587")
    #         logger.error("- Network/firewall allows outbound connections on port 587")
    #         return False
            
    #     except smtplib.SMTPSenderRefused as e:
    #         logger.error(f"Sender address refused: {e}")
    #         logger.error("Please check:")
    #         logger.error("- SMTP_FROM is a verified sender in Brevo dashboard")
    #         logger.error("- Sender email is properly verified in Brevo")
    #         return False
            
    #     except Exception as e:
    #         logger.error(f"Failed to send email via Brevo: {str(e)}")
    #         return False

    def send_email(self, to_email: str, subject: str, html_content: str, text_content: str = None) -> bool:
        """Send an email using Brevo SMTP and log queue info"""
        if not self._validate_configuration():
            logger.error("Brevo SMTP configuration validation failed")
            return False
        if not text_content:
            import re
            text_content = re.sub(r'<[^>]*>', '', html_content)
            text_content = re.sub(r'\s+', ' ', text_content).strip()
        
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr(("PaperBrain", self.smtp_from))
        msg["To"] = to_email
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                    server.ehlo()
                    if server.has_extn('STARTTLS'):
                        server.starttls()
                        server.ehlo()
            
                    server.login(self.smtp_user, self.smtp_pass)
                    # Send email
                    
                    response = server.sendmail(self.smtp_from, to_email, msg.as_string())

                    # ✅ Log queue info from server response
                    logger.info(f"Email sent to {to_email}. SMTP server response: {response.decode() if isinstance(response, bytes) else response}")

            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ Brevo SMTP authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send email via Brevo: {str(e)}")
            return False


    def send_verification_email(self, to_email: str, username: str, otp: str) -> bool:
        """Send email verification OTP using Brevo"""
        subject = "Verify Your PaperBrain Account"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f7f9; }}
                .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 40px 30px; }}
                .otp-container {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 25px 0; text-align: center; border: 2px dashed #e9ecef; }}
                .otp {{ font-size: 32px; font-weight: bold; color: #495057; letter-spacing: 3px; margin: 10px 0; font-family: 'Courier New', monospace; }}
                .footer {{ text-align: center; padding: 25px; color: #6c757d; font-size: 14px; background: #f8f9fa; border-top: 1px solid #e9ecef; }}
                .button {{ display: inline-block; padding: 14px 28px; background: #667eea; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
                @media (max-width: 600px) {{
                    .container {{ margin: 10px; border-radius: 8px; }}
                    .content {{ padding: 25px 20px; }}
                    .otp {{ font-size: 28px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>PaperBrain</h1>
                    <p>AI-Powered Document Intelligence</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #2c3e50; margin-top: 0;">Hi {username},</h2>
                    <p style="color: #555; font-size: 16px;">Welcome to PaperBrain! To complete your registration and start chatting with your documents, please verify your email address.</p>
                    
                    <div class="otp-container">
                        <p style="margin: 0 0 15px 0; color: #6c757d; font-size: 14px;">Your verification code:</p>
                        <div class="otp">{otp}</div>
                        <p style="margin: 15px 0 0 0; color: #dc3545; font-size: 13px; font-weight: 600;">⏰ Expires in 5 minutes</p>
                    </div>
                    
                    <p style="color: #555; font-size: 15px;">Enter this code in the verification page to activate your account and start using PaperBrain's powerful document AI features.</p>
                    
                    <p style="color: #6c757d; font-size: 14px; border-left: 4px solid #667eea; padding-left: 15px; margin: 25px 0;">
                        <strong>Note:</strong> If you didn't create a PaperBrain account, please ignore this email or contact our support team if you have concerns.
                    </p>
                    
                    <p style="color: #495057; margin-top: 30px;">
                        Happy document exploring!<br>
                        <strong>The PaperBrain Team</strong>
                    </p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0;">© 2024 PaperBrain. All rights reserved.</p>
                    <p style="margin: 10px 0 0 0; font-size: 12px; color: #adb5bd;">
                        This is an automated message. Please do not reply to this email.<br>
                        Need help? Contact our support team at support@paperbrain.com
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Verify Your PaperBrain Account

Hi {username},

Welcome to PaperBrain! To complete your registration, please use the verification code below:

Verification Code: {otp}

This code will expire in 5 minutes.

Enter this code in the verification page to activate your account and start using PaperBrain's powerful document AI features.

If you didn't create a PaperBrain account, please ignore this email.

Happy document exploring!
The PaperBrain Team

© 2024 PaperBrain. All rights reserved.
This is an automated message. Please do not reply to this email.
Need help? Contact our support team at support@paperbrain.com
"""
        
        return self.send_email(to_email, subject, html_content, text_content)

    def send_password_reset_email(self, to_email: str, username: str, reset_token: str) -> bool:
        """Send password reset email using Brevo"""
        subject = "Reset Your PaperBrain Password"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f7f9; }}
                .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }}
                .header {{ background: linear-gradient(135deg, #ff6b6b 0%, #ee5a52 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 40px 30px; }}
                .token-container {{ background: #fff5f5; border: 1px solid #ffe3e3; border-radius: 8px; padding: 20px; margin: 25px 0; }}
                .token {{ font-family: 'Courier New', monospace; font-size: 16px; color: #dc3545; word-break: break-all; padding: 15px; background: #fff; border-radius: 6px; border: 1px solid #ffe3e3; }}
                .footer {{ text-align: center; padding: 25px; color: #6c757d; font-size: 14px; background: #f8f9fa; border-top: 1px solid #e9ecef; }}
                .button {{ display: inline-block; padding: 14px 28px; background: #dc3545; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
                @media (max-width: 600px) {{
                    .container {{ margin: 10px; border-radius: 8px; }}
                    .content {{ padding: 25px 20px; }}
                    .token {{ font-size: 14px; padding: 12px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>PaperBrain</h1>
                    <p>Password Reset Request</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #2c3e50; margin-top: 0;">Hi {username},</h2>
                    <p style="color: #555; font-size: 16px;">We received a request to reset your PaperBrain password. Use the reset token below to set a new password:</p>
                    
                    <div class="token-container">
                        <p style="margin: 0 0 15px 0; color: #dc3545; font-size: 14px; font-weight: 600;">🔑 Your Password Reset Token:</p>
                        <div class="token">{reset_token}</div>
                        <p style="margin: 15px 0 0 0; color: #dc3545; font-size: 13px; font-weight: 600;">⏰ Expires in 15 minutes</p>
                    </div>
                    
                    <p style="color: #555; font-size: 15px;">Enter this token in the password reset form in the PaperBrain application to create a new password.</p>
                    
                    <p style="color: #6c757d; font-size: 14px; border-left: 4px solid #dc3545; padding-left: 15px; margin: 25px 0;">
                        <strong>Important:</strong> If you didn't request a password reset, please ignore this email. Your account remains secure.
                    </p>
                    
                    <p style="color: #495057; margin-top: 30px;">
                        Need immediate assistance?<br>
                        Contact our support team at support@paperbrain.com
                    </p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0;">© 2024 PaperBrain. All rights reserved.</p>
                    <p style="margin: 10px 0 0 0; font-size: 12px; color: #adb5bd;">
                        This is an automated message. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Reset Your PaperBrain Password

Hi {username},

We received a request to reset your PaperBrain password. Use the reset token below:

Reset Token: {reset_token}

This token will expire in 15 minutes.

Enter this token in the password reset form in the PaperBrain application to create a new password.

If you didn't request a password reset, please ignore this email. Your account remains secure.

Need immediate assistance? Contact our support team at support@paperbrain.com

© 2024 PaperBrain. All rights reserved.
This is an automated message. Please do not reply to this email.
"""
        
        return self.send_email(to_email, subject, html_content, text_content)

    def send_welcome_email(self, to_email: str, username: str) -> bool:
        """Send welcome email after successful verification using Brevo"""
        subject = "Welcome to PaperBrain - Your Account is Ready!"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f7f9; }}
                .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }}
                .header {{ background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 40px 30px; }}
                .feature {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 15px 0; border-left: 4px solid #4ecdc4; }}
                .footer {{ text-align: center; padding: 25px; color: #6c757d; font-size: 14px; background: #f8f9fa; border-top: 1px solid #e9ecef; }}
                .button {{ display: inline-block; padding: 14px 28px; background: #4ecdc4; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
                @media (max-width: 600px) {{
                    .container {{ margin: 10px; border-radius: 8px; }}
                    .content {{ padding: 25px 20px; }}
                    .feature {{ padding: 15px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>elcome to PaperBrain!</h1>
                    <p>Your Account is Ready</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #2c3e50; margin-top: 0;">Hi {username},</h2>
                    <p style="color: #555; font-size: 16px;">Congratulations! Your PaperBrain account has been successfully verified and is now ready to use.</p>
                    
                    <h3 style="color: #4ecdc4; margin: 30px 0 20px 0;">✨ What You Can Do Now:</h3>
                    
                    <div class="feature">
                        <strong style="color: #2c3e50; font-size: 16px;">📄 Upload Documents</strong>
                        <p style="color: #555; margin: 8px 0 0 0;">Upload PDFs and start chatting with your documents instantly.</p>
                    </div>
                    
                    <div class="feature">
                        <strong style="color: #2c3e50; font-size: 16px;">💬 AI-Powered Chat</strong>
                        <p style="color: #555; margin: 8px 0 0 0;">Ask questions about your documents and get intelligent answers powered by AI.</p>
                    </div>
                    
                    <div class="feature">
                        <strong style="color: #2c3e50; font-size: 16px;">🔍 Smart Search</strong>
                        <p style="color: #555; margin: 8px 0 0 0;">Find information across all your uploaded documents quickly and efficiently.</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://app.paperbrain.com/login" class="button">Get Started Now</a>
                    </div>
                    
                    <p style="color: #495057; margin-top: 30px;">
                        Ready to explore? Log in to your account and upload your first document!
                    </p>
                    
                    <p style="color: #6c757d; font-size: 14px; border-left: 4px solid #4ecdc4; padding-left: 15px; margin: 25px 0;">
                        <strong>Need help?</strong> Our documentation and support team are here to help you get the most out of PaperBrain.
                    </p>
                    
                    <p style="color: #495057;">
                        Happy document exploring!<br>
                        <strong>The PaperBrain Team</strong>
                    </p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0;">© 2024 PaperBrain. All rights reserved.</p>
                    <p style="margin: 10px 0 0 0; font-size: 12px; color: #adb5bd;">
                        This is an automated message. Please do not reply to this email.<br>
                        Support: support@paperbrain.com | Documentation: https://docs.paperbrain.com
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Welcome to PaperBrain!

Hi {username},

Congratulations! Your PaperBrain account has been successfully verified and is now ready to use.

What You Can Do Now:

📄 Upload Documents: Upload PDFs and start chatting with your documents instantly.

💬 AI-Powered Chat: Ask questions about your documents and get intelligent answers powered by AI.

🔍 Smart Search: Find information across all your uploaded documents quickly and efficiently.

Get started: https://app.paperbrain.com/login

Ready to explore? Log in to your account and upload your first document!

Need help? Our documentation and support team are here to help you get the most out of PaperBrain.

Happy document exploring!
The PaperBrain Team

© 2024 PaperBrain. All rights reserved.
Support: support@paperbrain.com
Documentation: https://docs.paperbrain.com
"""
        
        return self.send_email(to_email, subject, html_content, text_content)

# Create singleton instance
email_service = EmailService()
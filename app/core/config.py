import json
from pydantic_settings import BaseSettings
from pydantic import Field, PostgresDsn, RedisDsn, validator
from typing import List
from typing import Optional, List

# Import logger directly without circular dependency
import logging
logger = logging.getLogger("paperbrain")

class Settings(BaseSettings):
    # App
    APP_NAME: str = Field("PaperBrain API", env="APP_NAME")
    APP_ENV: str = Field("development", env="APP_ENV")
    DEBUG: bool = Field(False, env="DEBUG")
    
    # Database
    DATABASE_URL: PostgresDsn = Field(..., env="DATABASE_URL")
    
    # Redis
    REDIS_URL: str = Field(..., env="REDIS_URL")  # host:port or full url
    REDIS_PASSWORD: Optional[str] = Field(None, env="REDIS_PASSWORD")
    
    # JWT
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ALGORITHM: str = Field("HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    
    # Google Gemini (replaced OpenAI)
    GEMINI_API_KEY: str = Field(..., env="GEMINI_API_KEY")
    GEMINI_MODEL: str = Field("gemini-1.5-flash", env="GEMINI_MODEL")  # or gemini-1.5-pro
    GEMINI_TEMPERATURE: float = Field(0.7, env="GEMINI_TEMPERATURE")
    GEMINI_MAX_TOKENS: int = Field(500, env="GEMINI_MAX_TOKENS")
    
    # Email - Brevo SMTP Configuration
    SMTP_HOST: str = Field(..., env="SMTP_HOST")
    SMTP_PORT: int = Field(587, env="SMTP_PORT")
    SMTP_USER: str = Field(..., env="SMTP_USER")
    SMTP_PASS: str = Field(..., env="SMTP_PASS")
    SMTP_FROM: str = Field(..., env="SMTP_FROM")
    
    # Vector Store
    VECTOR_BACKEND: str = Field("pinecone", env="VECTOR_BACKEND")
    PINECONE_API_KEY: Optional[str] = Field(None, env="PINECONE_API_KEY")
    PINECONE_ENVIRONMENT: Optional[str] = Field(None, env="PINECONE_ENVIRONMENT")
    PINECONE_INDEX: Optional[str] = Field("rag-index", env="PINECONE_INDEX")
    PINECONE_REGION: str = "us-west-1"  # default if not in env
    PINECONE_CLOUD: str = "aws"         # default if not in env
    
    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=[],
        description="Allowed CORS origins"
    )
    @property
    def cors_origins_list(self) -> List[str]:
        """
        Return CORS origins as a list.
        Falls back to ["*"] if none provided.
        """
        if not self.CORS_ORIGINS:
            return ["*"]
        return self.CORS_ORIGINS

    # File Upload
    MAX_FILE_SIZE: int = Field(10 * 1024 * 1024, env="MAX_FILE_SIZE")  # 10MB
    
    @property
    def redis_dsn(self) -> str:
        """
        Build a proper Redis DSN string for libraries that expect it.
        Example: redis://:password@host:port/0
        """
        if self.REDIS_URL.startswith("redis://"):
            return self.REDIS_URL  # already a full DSN                   
        if not self.REDIS_PASSWORD:
            raise ValueError("❌ REDIS_PASSWORD is required when using host:port in REDIS_URL")    
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_URL}/0"

    # Validators
    @validator('CORS_ORIGINS', pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from JSON string to list"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse CORS_ORIGINS as JSON: {v}")
                return ["http://localhost:5173","https://paperbrain-xi.vercel.app"]
        return v
    
    @validator('GEMINI_MODEL')
    def validate_gemini_model(cls, v):
        """Validate Gemini model name"""
        valid_models = [
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-pro",
            "gemini-pro-vision"
        ]
        if v not in valid_models:
            logger.warning(f"GEMINI_MODEL '{v}' is not in the list of common models: {valid_models}")
        return v
    
    @validator('GEMINI_TEMPERATURE')
    def validate_temperature(cls, v):
        """Validate temperature is between 0 and 2"""
        if not 0 <= v <= 2:
            raise ValueError("GEMINI_TEMPERATURE must be between 0 and 2")
        return v
    
    @validator('GEMINI_MAX_TOKENS')
    def validate_max_tokens(cls, v):
        """Validate max tokens is reasonable"""
        if v < 1 or v > 8192:
            logger.warning(f"GEMINI_MAX_TOKENS {v} is outside typical range (1-8192)")
        return v
    
    @validator('SMTP_HOST')
    def validate_smtp_host(cls, v):
        """Validate SMTP host configuration"""
        if not v:
            raise ValueError("SMTP_HOST is required for email functionality")
        
        # Warn if not using Brevo but don't block
        if 'brevo.com' not in v:
            logger.warning(f"SMTP_HOST ({v}) doesn't appear to be Brevo. Brevo uses smtp-relay.brevo.com")
        
        return v
    
    @validator('SMTP_PORT')
    def validate_smtp_port(cls, v):
        """Validate SMTP port"""
        if v not in [587, 465, 2525]:
            logger.warning(f"SMTP_PORT {v} is unusual. Common ports: 587 (TLS), 465 (SSL), 2525 (Mailtrap)")
        return v
    
    @validator('SMTP_FROM')
    def validate_smtp_from(cls, v):
        """Validate FROM email address"""
        if not v:
            raise ValueError("SMTP_FROM is required")
        
        # Basic email format validation
        if '@' not in v or '.' not in v.split('@')[-1]:
            logger.warning(f"SMTP_FROM ({v}) doesn't appear to be a valid email address")
        
        return v
    
    @validator('SMTP_USER')
    def validate_smtp_user(cls, v, values):
        """Validate SMTP username"""
        if not v:
            raise ValueError("SMTP_USER is required")
        
        # For Brevo, the SMTP_USER should be your login email, not the from address
        smtp_host = values.get('SMTP_HOST', '')
        if 'brevo.com' in smtp_host and values.get('SMTP_FROM') and v == values.get('SMTP_FROM'):
            logger.warning("For Brevo, SMTP_USER should be your login email, not the from address")
        
        return v
    
    def validate_email_config(self) -> dict:
        """
        Validate email configuration and return status
        """
        validation_result = {
            'valid': True,
            'missing_fields': [],
            'warnings': [],
            'provider': 'unknown'
        }
        
        # Check required fields
        required_fields = {
            'SMTP_HOST': self.SMTP_HOST,
            'SMTP_USER': self.SMTP_USER,
            'SMTP_PASS': self.SMTP_PASS,
            'SMTP_FROM': self.SMTP_FROM
        }
        
        for field_name, field_value in required_fields.items():
            if not field_value:
                validation_result['valid'] = False
                validation_result['missing_fields'].append(field_name)
        
        # Detect provider
        if 'brevo.com' in self.SMTP_HOST:
            validation_result['provider'] = 'brevo'
        elif 'gmail.com' in self.SMTP_HOST:
            validation_result['provider'] = 'gmail'
        elif 'mailtrap.io' in self.SMTP_HOST:
            validation_result['provider'] = 'mailtrap'
        elif 'sendgrid.net' in self.SMTP_HOST:
            validation_result['provider'] = 'sendgrid'
        elif 'elasticemail.com' in self.SMTP_HOST:
            validation_result['provider'] = 'elasticemail'
        
        # Provider-specific validations
        if validation_result['provider'] == 'brevo':
            if self.SMTP_PORT != 587:
                validation_result['warnings'].append("Brevo typically uses port 587 for TLS")
            
            # Check if SMTP_USER looks like a login email (not from address)
            if self.SMTP_FROM and self.SMTP_USER == self.SMTP_FROM:
                validation_result['warnings'].append(
                    "For Brevo, SMTP_USER should be your login email, not the from address"
                )
        
        elif validation_result['provider'] == 'gmail':
            if self.SMTP_PORT not in [587, 465]:
                validation_result['warnings'].append("Gmail uses ports 587 (TLS) or 465 (SSL)")
            
            # Check for app password pattern (Gmail app passwords are 16 characters)
            if self.SMTP_PASS and len(self.SMTP_PASS) != 16 and not self.SMTP_PASS.startswith('your-'):
                validation_result['warnings'].append(
                    "Gmail requires an App Password (16 characters), not your regular password"
                )
        
        return validation_result
    
    def is_email_configured(self) -> bool:
        """Check if email is properly configured"""
        return all([self.SMTP_HOST, self.SMTP_USER, self.SMTP_PASS, self.SMTP_FROM])
    
    def get_email_config_status(self) -> str:
        """Get human-readable email configuration status"""
        if not self.is_email_configured():
            return "❌ Not configured - missing required fields"
        
        validation = self.validate_email_config()
        
        if not validation['valid']:
            return f"❌ Invalid configuration - missing: {', '.join(validation['missing_fields'])}"
        
        status = f"Configured for {validation['provider'].upper()}"
        if validation['warnings']:
            status += f" with warnings: {', '.join(validation['warnings'])}"
        
        return status
    
    def is_gemini_configured(self) -> bool:
        """Check if Gemini is properly configured"""
        return bool(self.GEMINI_API_KEY)
    
    def get_gemini_config_status(self) -> str:
        """Get human-readable Gemini configuration status"""
        if not self.is_gemini_configured():
            return "❌ Not configured - GEMINI_API_KEY missing"
        
        return f"✅ Configured - Model: {self.GEMINI_MODEL}, Temp: {self.GEMINI_TEMPERATURE}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        validate_all = True

# Create settings instance
settings = Settings()

# Now configure logger based on settings
def configure_logger():
    """Configure logger based on settings"""
    # Set log level based on DEBUG setting
    if settings.DEBUG:
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    else:
        logger.setLevel(logging.INFO)
        for handler in logger.handlers:
            handler.setLevel(logging.INFO)

# Configure logger after settings are loaded
configure_logger()

# Validate settings on import
try:
    email_status = settings.get_email_config_status()
    gemini_status = settings.get_gemini_config_status()
    
    logger.info(f"Email configuration: {email_status}")
    logger.info(f"Gemini configuration: {gemini_status}")
    
    # Log additional configuration info
    logger.info(f"App environment: {settings.APP_ENV}")
    logger.info(f"Database: {'Configured' if settings.DATABASE_URL else '❌ Not configured'}")
    logger.info(f"Redis: {'Configured' if settings.REDIS_URL else '❌ Not configured'}")
    
except Exception as e:
    logger.error(f"Error validating settings: {e}")
    # Don't raise here to allow the app to start with partial configuration
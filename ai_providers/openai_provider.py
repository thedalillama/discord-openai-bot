"""
OpenAI provider implementation with image generation support.
"""
from openai import OpenAI
import base64
import io
from .base import AIProvider
from config import OPENAI_API_KEY, AI_MODEL, DEFAULT_TEMPERATURE
from utils.logging_utils import get_logger

class OpenAIProvider(AIProvider):
    """OpenAI provider using responses API for both text and image generation"""
    
    def __init__(self):
        super().__init__()
        self.name = "openai"
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = AI_MODEL
        self.max_context_length = 128000  # GPT-4o context window
        self.max_response_tokens = 300    # Our current safe limit
        self.supports_images = True
        self.logger = get_logger('openai')
    
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None, channel_id=None):
        """
        Generate an AI response using OpenAI's Responses API.
        Returns structured response with text and optional images.
        
        Args:
            messages: List of message objects with role and content
            max_tokens: Maximum number of tokens in the response
            temperature: Creativity of the response (0.0-1.0)
            channel_id: Optional Discord channel ID (not used by OpenAI provider)
        """
        self.logger.debug(f"Using OpenAI provider (model: {self.model}) for API call")
        
        # Use default values if not specified
        if max_tokens is None:
            max_tokens = self.max_response_tokens
        if temperature is None:
            temperature = DEFAULT_TEMPERATURE
        
        # Log the system prompt being sent to API
        system_prompt = None
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
                break
        
        if system_prompt:
            self.logger.debug(f"Sending system prompt to OpenAI API: '{system_prompt}'")
        
        self.logger.debug(f"Number of messages: {len(messages)}")
        
        # Convert messages to input format for Responses API
        input_text = self._convert_messages_to_input(messages)
        
        self.logger.debug(f"Converted {len(messages)} messages to input text for Responses API")
        
        try:
            response = self.client.responses.create(
                model=self.model,
                input=input_text,
                tools=[{"type": "image_generation"}]
            )
            
            self.logger.debug(f"Responses API call completed successfully")
            
            # Extract text response from output_text attribute
            text_response = ""
            if hasattr(response, 'output_text') and response.output_text:
                text_response = str(response.output_text).strip()
                self.logger.debug(f"Extracted text response: {len(text_response)} characters")
            
            # Extract any generated images from the output
            images = []
            
            if hasattr(response, 'output') and response.output:
                self.logger.debug(f"Found {len(response.output)} output items")
                for i, output in enumerate(response.output):
                    if hasattr(output, 'type') and output.type == "image_generation_call":
                        try:
                            if hasattr(output, 'result') and output.result:
                                # Decode the base64 image data
                                image_data = base64.b64decode(output.result)
                                images.append({
                                    "data": image_data,
                                    "format": "png",
                                    "base64": output.result
                                })
                                self.logger.debug(f"Successfully processed generated image {i+1}")
                        except Exception as e:
                            self.logger.error(f"Error processing generated image {i+1}: {e}")
            
            # Determine what tools were called
            tools_called = ["image_generation"] if images else []
            
            # If we have images but no text, provide a helpful default message
            if images and not text_response:
                text_response = "Here's the image you requested!"
                self.logger.debug("Added default text for image-only response")
            
            # If we have neither text nor images, this might be an error
            if not text_response and not images:
                self.logger.warning("No text or images found in Responses API response")
                text_response = "I apologize, but I wasn't able to generate a response. Please try again."
            
            self.logger.debug(f"OpenAI Responses API response: text={bool(text_response)}, images={len(images)}")
            
            return {
                "text": text_response,
                "images": images,
                "metadata": {
                    "model_used": self.model,
                    "tools_called": tools_called
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error generating AI response from OpenAI: {e}")
            raise e
    
    def _convert_messages_to_input(self, messages):
        """
        Convert OpenAI chat messages format to single input string for Responses API
        """
        input_parts = []
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                input_parts.append(f"System: {content}")
            elif role == "user":
                # Extract name if available
                name = msg.get("name", "User")
                input_parts.append(f"{name}: {content}")
            elif role == "assistant":
                input_parts.append(f"Assistant: {content}")
        
        return "\n\n".join(input_parts)

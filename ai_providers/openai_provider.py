"""
OpenAI provider implementation with image generation support.
"""
from openai import OpenAI
import base64
import io
from .base import AIProvider
from config import OPENAI_API_KEY, AI_MODEL, DEFAULT_TEMPERATURE, ENABLE_IMAGE_GENERATION
from utils.logging_utils import get_logger

class OpenAIProvider(AIProvider):
    """OpenAI provider using chat completions API and responses API for image generation"""
    
    # Models that support image generation via Responses API
    SUPPORTED_IMAGE_MODELS = [
        'gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano', 'o3'
    ]
    
    def __init__(self):
        super().__init__()
        self.name = "openai"
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = AI_MODEL
        self.max_context_length = 128000  # GPT-4o context window
        self.max_response_tokens = 300    # Our current safe limit
        self.supports_images = True       # For future use
        self.logger = get_logger('openai')
    
    def _supports_image_generation(self):
        """Check if current model supports image generation"""
        return (ENABLE_IMAGE_GENERATION and 
                self.model in self.SUPPORTED_IMAGE_MODELS)
    
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None):
        """
        Generate an AI response using OpenAI's API.
        Returns structured response with text and optional images.
        """
        self.logger.debug(f"Using OpenAI provider (model: {self.model}) for API call")
        
        try:
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
            
            # Check if we should use Responses API (for image generation) or Chat Completions API
            if self._supports_image_generation():
                self.logger.debug("Using Responses API with image generation capability - letting AI decide when to use it")
                return await self._generate_with_responses_api(messages, max_tokens, temperature)
            else:
                self.logger.debug("Using Chat Completions API (no image generation)")
                return await self._generate_with_chat_api(messages, max_tokens, temperature)
                
        except Exception as e:
            self.logger.error(f"Error generating AI response from OpenAI: {e}")
            raise e
    
    async def _generate_with_chat_api(self, messages, max_tokens, temperature):
        """Generate response using traditional Chat Completions API"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            n=1,
            temperature=temperature
        )
        
        raw_response = response.choices[0].message.content.strip()
        finish_reason = response.choices[0].finish_reason
        
        # Check if the response was cut off due to length
        if finish_reason == "length":
            self.logger.warning(f"Response was truncated due to token limit")
            raw_response += "\n\n[Note: Response was truncated due to length. Feel free to ask for more details.]"
        
        self.logger.debug(f"OpenAI Chat API response received successfully")
        
        # Return structured format for consistency
        return {
            "text": raw_response,
            "images": [],
            "metadata": {
                "model_used": self.model,
                "finish_reason": finish_reason,
                "tools_called": []
            }
        }
    
    async def _generate_with_responses_api(self, messages, max_tokens, temperature):
        """Generate response using Responses API with image generation capability"""
        
        # Convert messages to input format for Responses API
        input_text = self._convert_messages_to_input(messages)
        
        self.logger.debug(f"Converted {len(messages)} messages to input text for Responses API")
        
        try:
            response = self.client.responses.create(
                model=self.model,
                input=input_text,
                tools=[{"type": "image_generation"}]
            )
            
            # Debug: Log the full response structure
            self.logger.debug(f"Full response type: {type(response)}")
            if hasattr(response, '__dict__'):
                self.logger.debug(f"Response attributes: {list(response.__dict__.keys())}")
            
            # The issue might be that we need to iterate through the response properly
            # Let's try to extract both text and images from the response structure
            text_response = ""
            images = []
            
            # Try to access the response content - this might be the key issue
            if hasattr(response, 'content'):
                self.logger.debug(f"Response has content attribute of type: {type(response.content)}")
                
                # If content is a string, use it directly
                if isinstance(response.content, str):
                    text_response = response.content
                # If content is a list, iterate through it
                elif isinstance(response.content, list):
                    for item in response.content:
                        self.logger.debug(f"Content item type: {type(item)}")
                        if hasattr(item, 'text'):
                            text_response += str(item.text)
                        elif hasattr(item, 'type') and item.type == 'text':
                            text_response += str(item.content) if hasattr(item, 'content') else str(item)
                # If content is an object, try to get text from it
                elif hasattr(response.content, 'text'):
                    text_response = str(response.content.text)
                else:
                    self.logger.debug(f"Content structure: {dir(response.content)}")
            
            # If we still don't have text and this is not generating an image, there might be an issue
            if not text_response:
                # Check if there are any images being generated
                has_images = False
                if hasattr(response, 'output') and response.output:
                    has_images = any(hasattr(output, 'type') and output.type == "image_generation_call" 
                                   for output in response.output)
                
                if has_images:
                    text_response = "Here's the image you requested!"
                else:
                    # If no images and no text, something went wrong - fall back to chat API
                    self.logger.warning("No text content found in Responses API response, falling back to Chat API")
                    return await self._generate_with_chat_api(messages, max_tokens, temperature)
            
            # Extract any generated images
            images = []
            
            # Check different possible response structures
            if hasattr(response, 'output') and response.output:
                for output in response.output:
                    if hasattr(output, 'type') and output.type == "image_generation_call":
                        try:
                            image_data = base64.b64decode(output.result)
                            images.append({
                                "data": image_data,
                                "format": "png",
                                "base64": output.result
                            })
                            self.logger.debug(f"Successfully processed generated image")
                        except Exception as e:
                            self.logger.error(f"Error processing generated image: {e}")
            
            # Also check if images are in content blocks
            if hasattr(response, 'content') and isinstance(response.content, list):
                for content_block in response.content:
                    if hasattr(content_block, 'type') and content_block.type == "image":
                        try:
                            # Handle image content blocks
                            if hasattr(content_block, 'data'):
                                image_data = base64.b64decode(content_block.data)
                                images.append({
                                    "data": image_data,
                                    "format": "png",
                                    "base64": content_block.data
                                })
                                self.logger.debug(f"Successfully processed image from content block")
                        except Exception as e:
                            self.logger.error(f"Error processing image from content block: {e}")
            
            tools_called = ["image_generation"] if images else []
            
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
            self.logger.error(f"Error in Responses API call: {e}")
            # Fall back to chat completions API
            self.logger.info("Falling back to Chat Completions API")
            return await self._generate_with_chat_api(messages, max_tokens, temperature)
    
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

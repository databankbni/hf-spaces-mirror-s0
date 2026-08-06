"""
Image Generation for mktbook_4: The Synthetic Studio Economy

Uses DALL-E 3 to generate fashion imagery based on agent descriptions.
Manages image storage, IP compliance checking, and URL management.
"""

import os
import logging
import httpx
from typing import Optional, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Generate fashion images using DALL-E 3."""
    
    def __init__(self, openai_client, config):
        """
        Args:
            openai_client: OpenAI async client
            config: Configuration manager
        """
        self.client = openai_client
        self.config = config
        self.model = "dall-e-3"
        self.image_dir = Path("/opt/mktbook/generated_images") if os.path.exists("/opt/mktbook") else Path("./generated_images")
        self.image_dir.mkdir(exist_ok=True)
    
    async def generate_fashion_image(self, prompt: str, fashion_description: str, 
                                   style_guide: str = "") -> Tuple[str, Optional[str]]:
        """
        Generate fashion image with DALL-E 3.
        
        Args:
            prompt: Original fashion description
            fashion_description: Expanded fashion narrative
            style_guide: Optional style constraints (e.g., "minimalist", "luxury")
        
        Returns:
            (image_url, local_path) tuple
        """
        
        # Build comprehensive prompt
        refined_prompt = self._build_dall_e_prompt(
            prompt, fashion_description, style_guide
        )
        
        try:
            logger.info(f"Generating image for: {prompt[:50]}...")
            
            response = await self.client.images.generate(
                model=self.model,
                prompt=refined_prompt,
                size="1024x1024",
                quality="hd",
                n=1,
                style="natural"
            )
            
            image_url = response.data[0].url
            logger.info(f"Image generated: {image_url}")
            
            # Download and save locally
            local_path = await self._download_and_save(image_url, prompt)
            
            return image_url, local_path
        
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return "", None
    
    def _build_dall_e_prompt(self, base_prompt: str, fashion_description: str,
                            style_guide: str) -> str:
        """Build comprehensive DALL-E prompt with constraints."""
        
        # Start with base
        prompt = f"Fashion photograph: {fashion_description}\n"
        
        # Add style constraints
        if style_guide:
            prompt += f"Style: {style_guide}\n"
        
        # Add quality requirements
        prompt += (
            "Requirements: High-end fashion photography, professional lighting, "
            "clean background, sharp focus on garment details, magazine-quality.\n"
        )
        
        # Add negative prompts
        prompt += (
            "Avoid: Branded logos, copyright symbols, protected imagery, "
            "blurry details, amateur photography, watermarks, text overlays.\n"
        )
        
        # Add diversity constraint
        prompt += "Include diverse model representation. Modern, inclusive aesthetic."
        
        return prompt
    
    async def _download_and_save(self, image_url: str, description: str) -> str:
        """
        Download image from URL and save locally.
        
        Args:
            image_url: DALL-E image URL
            description: Fashion description for filename
        
        Returns:
            Local file path
        """
        try:
            # Create filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_desc = description[:30].replace(" ", "_").lower()
            filename = f"{timestamp}_{safe_desc}.png"
            filepath = self.image_dir / filename
            
            # Download image
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=30.0)
                response.raise_for_status()
            
            # Save to disk
            with open(filepath, "wb") as f:
                f.write(response.content)
            
            logger.info(f"Image saved: {filepath}")
            return str(filepath)
        
        except Exception as e:
            logger.error(f"Error downloading/saving image: {e}")
            return ""
    
    def get_image_urls_for_discord(self, local_paths: list) -> list:
        """
        Convert local image paths to Discord-accessible URLs.
        For Discord embedding, we'll return file:// URLs or upload to service.
        """
        # In production, images would be uploaded to S3, CDN, or Discord attachment
        # For now, return local paths that could be converted to file:///
        return [f"file:///{path}" for path in local_paths if path]
    
    def check_ip_compliance(self, prompt: str, description: str) -> Tuple[bool, list]:
        """
        Check for potential copyright violations in image description.
        
        Args:
            prompt: Original prompt
            description: Fashion description
        
        Returns:
            (is_compliant, flagged_items)
        """
        # List of protected/high-risk brand names
        protected_brands = {
            "chanel", "gucci", "dior", "louis vuitton", "hermes", "prada",
            "balenciaga", "fendi", "celine", "loewe", "valentino", "armani",
            "versace", "burberry", "coach", "cartier", "rolex", "hermès"
        }
        
        combined_text = f"{prompt} {description}".lower()
        flagged = []
        
        for brand in protected_brands:
            if brand in combined_text:
                flagged.append(brand)
        
        # Also check for exact logo/symbol references
        logo_patterns = ["logo", "monogram", "insignia", "trademark", "brand mark"]
        for pattern in logo_patterns:
            if pattern in combined_text:
                flagged.append(f"Logo reference: {pattern}")
        
        is_compliant = len(flagged) == 0
        
        if not is_compliant:
            logger.warning(f"IP compliance issue: {flagged}")
        
        return is_compliant, flagged

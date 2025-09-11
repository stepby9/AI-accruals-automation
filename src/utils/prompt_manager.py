import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class PromptManager:
    """Manages AI prompts loaded from external YAML files"""
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        if prompts_dir is None:
            self.prompts_dir = Path(__file__).parent.parent.parent / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)
        
        self._prompts_cache = {}
        self._load_all_prompts()
        
        logger.info(f"Prompt manager initialized with {len(self._prompts_cache)} prompts from {self.prompts_dir}")

    def _load_all_prompts(self):
        """Load all prompt files from the prompts directory"""
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory does not exist: {self.prompts_dir}")
            return
        
        for prompt_file in self.prompts_dir.glob("*.yaml"):
            try:
                self._load_prompt_file(prompt_file)
            except Exception as e:
                logger.error(f"Failed to load prompt file {prompt_file}: {str(e)}")

    def _load_prompt_file(self, file_path: Path):
        """Load a single prompt file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                prompt_config = yaml.safe_load(f)
            
            # Validate required fields
            required_fields = ['name', 'system_prompt', 'user_prompt_template']
            for field in required_fields:
                if field not in prompt_config:
                    raise ValueError(f"Missing required field: {field}")
            
            prompt_name = prompt_config['name']
            self._prompts_cache[prompt_name] = prompt_config
            
            logger.debug(f"Loaded prompt: {prompt_name} from {file_path.name}")
            
        except Exception as e:
            logger.error(f"Error loading prompt file {file_path}: {str(e)}")
            raise

    def get_prompt_config(self, prompt_name: str) -> Dict[str, Any]:
        """Get the full prompt configuration"""
        if prompt_name not in self._prompts_cache:
            raise ValueError(f"Prompt '{prompt_name}' not found. Available prompts: {list(self._prompts_cache.keys())}")
        
        return self._prompts_cache[prompt_name].copy()

    def get_system_prompt(self, prompt_name: str) -> str:
        """Get the system prompt for a given prompt name"""
        config = self.get_prompt_config(prompt_name)
        return config['system_prompt'].strip()

    def get_user_prompt(self, prompt_name: str, **template_vars) -> str:
        """Get the user prompt with template variables filled in"""
        config = self.get_prompt_config(prompt_name)
        template = config['user_prompt_template']
        
        try:
            # Fill in template variables
            filled_prompt = template.format(**template_vars)
            return filled_prompt.strip()
            
        except KeyError as e:
            missing_var = str(e).strip("'")
            logger.error(f"Missing template variable '{missing_var}' for prompt '{prompt_name}'")
            raise ValueError(f"Missing template variable: {missing_var}")
        except Exception as e:
            logger.error(f"Error formatting prompt template for '{prompt_name}': {str(e)}")
            raise

    def get_model_config(self, prompt_name: str) -> Dict[str, Any]:
        """Get the model configuration (model, temperature, max_tokens, etc.)"""
        config = self.get_prompt_config(prompt_name)
        
        model_config = {
            'model': config.get('model', 'gpt-4')
        }
        
        # Handle both max_tokens (older models) and max_completion_tokens (GPT-5)
        if 'max_completion_tokens' in config:
            model_config['max_completion_tokens'] = config.get('max_completion_tokens', 1000)
        else:
            model_config['max_tokens'] = config.get('max_tokens', 1000)
        
        # Only add temperature for models that support it (not GPT-5)
        if 'temperature' in config and config.get('model', '').lower() != 'gpt-5':
            model_config['temperature'] = config.get('temperature', 0.1)
        
        return model_config

    def reload_prompts(self):
        """Reload all prompts from disk"""
        logger.info("Reloading all prompts from disk")
        self._prompts_cache.clear()
        self._load_all_prompts()

    def reload_prompt(self, prompt_name: str):
        """Reload a specific prompt from disk"""
        prompt_file = self.prompts_dir / f"{prompt_name}.yaml"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        logger.info(f"Reloading prompt: {prompt_name}")
        self._load_prompt_file(prompt_file)

    def list_available_prompts(self) -> list[str]:
        """Get list of available prompt names"""
        return list(self._prompts_cache.keys())

    def get_prompt_info(self, prompt_name: str) -> Dict[str, Any]:
        """Get metadata about a prompt"""
        config = self.get_prompt_config(prompt_name)
        
        return {
            'name': config['name'],
            'version': config.get('version', 'unknown'),
            'description': config.get('description', 'No description'),
            'model': config.get('model', 'gpt-4'),
            'template_vars': self._extract_template_vars(config['user_prompt_template'])
        }

    def _extract_template_vars(self, template: str) -> list[str]:
        """Extract template variable names from a template string"""
        import re
        # Find all {variable_name} patterns
        matches = re.findall(r'\{([^}]+)\}', template)
        return list(set(matches))

    def validate_template_vars(self, prompt_name: str, **template_vars) -> Dict[str, Any]:
        """Validate that all required template variables are provided"""
        config = self.get_prompt_config(prompt_name)
        template = config['user_prompt_template']
        required_vars = self._extract_template_vars(template)
        
        provided_vars = set(template_vars.keys())
        required_vars_set = set(required_vars)
        
        missing_vars = required_vars_set - provided_vars
        extra_vars = provided_vars - required_vars_set
        
        return {
            'valid': len(missing_vars) == 0,
            'missing_vars': list(missing_vars),
            'extra_vars': list(extra_vars),
            'required_vars': required_vars
        }

# Global instance
_prompt_manager = None

def get_prompt_manager() -> PromptManager:
    """Get the global prompt manager instance"""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager

# Convenience functions for common operations
def get_system_prompt(prompt_name: str) -> str:
    """Convenience function to get system prompt"""
    return get_prompt_manager().get_system_prompt(prompt_name)

def get_user_prompt(prompt_name: str, **template_vars) -> str:
    """Convenience function to get user prompt with variables"""
    return get_prompt_manager().get_user_prompt(prompt_name, **template_vars)

def get_model_config(prompt_name: str) -> Dict[str, Any]:
    """Convenience function to get model configuration"""
    return get_prompt_manager().get_model_config(prompt_name)
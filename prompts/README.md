# AI Prompts Directory

This directory contains AI prompts used by the Finance Accruals Automation system. Prompts are stored as YAML files for easy editing and version control.

## Available Prompts

### `accrual_analysis.yaml`
- **Purpose**: Analyzes PO lines to determine monthly accrual needs
- **AI Model**: GPT-4
- **Used by**: `AccrualEngine` class
- **Key Features**: 
  - Business rules enforcement
  - Currency-aware calculations
  - Monthly accrual estimation

### `invoice_extraction.yaml`
- **Purpose**: Extracts structured data from invoice documents
- **AI Model**: GPT-4 Vision
- **Used by**: `InvoiceProcessor` class
- **Key Features**:
  - Multi-format support (PDF, Excel, Word, Images)
  - Foreign language translation
  - Service period detection

## YAML File Structure

```yaml
version: "1.0"
name: "prompt_name"
description: "Brief description of the prompt"

system_prompt: |
  System-level instructions for the AI...

user_prompt_template: |
  User prompt with template variables like {variable_name}...
  
# Model configuration
model: "gpt-4"
max_tokens: 1000
temperature: 0.1
```

## Template Variables

Prompts can use template variables (e.g., `{current_date}`) that get replaced at runtime:

- **accrual_analysis.yaml variables:**
  - `current_date`, `current_month`
  - `po_id`, `line_id`, `vendor_name`, `gl_account`
  - `amount`, `amount_usd`, `remaining_balance`, `remaining_balance_usd`
  - `currency`, `delivery_date`, `prepaid_start_date`, `prepaid_end_date`
  - `bills_section`, `invoices_section`

- **invoice_extraction.yaml variables:**
  - `content_section` (for text or image content)

## Editing Prompts

### Safe Editing Guidelines

1. **Always validate YAML syntax** before saving
2. **Test template variables** - ensure all `{variables}` are provided by the code
3. **Keep JSON response format consistent** - don't change field names without updating code
4. **Preserve the overall structure** - system_prompt, user_prompt_template, model config

### Business Rule Changes

To modify accrual business rules:

1. Edit `accrual_analysis.yaml`
2. Modify the `BUSINESS RULES` or `ANALYSIS INSTRUCTIONS` sections
3. Test with a small batch before production use

### Model Configuration

Change AI behavior by adjusting:
- `model`: Which OpenAI model to use
- `temperature`: Creativity level (0.0 = deterministic, 1.0 = creative)
- `max_tokens`: Maximum response length

## Version Control

- Each prompt file has a `version` field for tracking changes
- Consider updating version numbers when making significant changes
- Document changes in git commit messages

## Testing Prompts

Use the prompt manager utilities for testing:

```python
from src.utils.prompt_manager import get_prompt_manager

pm = get_prompt_manager()

# Validate template variables
validation = pm.validate_template_vars("accrual_analysis", 
    current_date="2024-01-15", po_id="PO123", ...)

# Test prompt generation
user_prompt = pm.get_user_prompt("accrual_analysis", **template_vars)
```

## Troubleshooting

### Common Issues

1. **YAML Syntax Errors**: Use a YAML validator
2. **Missing Template Variables**: Check the validation output
3. **Model Errors**: Verify model names in OpenAI documentation

### Reloading Prompts

Prompts are cached for performance. To reload after changes:

```python
from src.utils.prompt_manager import get_prompt_manager
get_prompt_manager().reload_prompts()
```

## Best Practices

1. **Keep prompts focused** - Each prompt should have a single, clear purpose
2. **Use descriptive variable names** - `{current_date}` not `{date}`
3. **Include examples** in prompts when helpful
4. **Test thoroughly** after changes
5. **Document significant changes** in git commits
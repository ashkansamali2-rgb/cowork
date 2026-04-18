import pathlib

def skill_save_document_content(*args, **kwargs):
    """
    Saves text content to a specified file. 
    Used as a fallback for creating documents when specialized tools fail.
    
    Args:
        filename (str): The name/path of the file to create.
        content (str): The text content to write into the file.
    """
    try:
        filename = kwargs.get('filename') or (args[0] if len(args) > 0 else "document.txt")
        content = kwargs.get('content') or (args[1] if len(args) > 1 else "")
        
        if not content:
            return "Error: No content provided to save."
            
        path = pathlib.Path(filename)
        path.write_text(content, encoding='utf-8')
        
        return f"Successfully saved content to {filename}"
    except Exception as e:
        return f"Failed to save document: {str(e)}"
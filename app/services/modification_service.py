from typing import Dict, List, Any
import google.generativeai as genai
import json
import os
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class DiagramModifier:
    """Service for intelligently modifying existing diagrams using AI"""
    
    def __init__(self):
        # Initialize Gemini
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Architecture diagram modification prompt
        self.architecture_modification_prompt = """
You are an expert system architect modifying architecture diagrams.

CONVERSATION HISTORY:
{conversation_history}

CURRENT DIAGRAM (JSON):
{current_diagram}

USER REQUEST: "{modification_request}"

MODIFICATION RULES:
1. ADD: If request says "add X", create a new node for X with appropriate icon from available icons
2. REMOVE: If request says "remove X" or "delete X", DELETE all nodes containing X in their label
3. UPDATE: If request says "change X to Y" or "make X use Y", UPDATE existing node X
4. CONNECT: If request says "connect X to Y", add an edge between them
5. If a component already exists, UPDATE it instead of creating duplicate

AVAILABLE ICONS: {available_icons}

CONTEXT INSTRUCTIONS:
- Use the conversation history to understand previous versions and maintain consistency
- Ensure modifications align with the architectural context from past versions
- Avoid duplicating components unnecessarily based on history
- Select appropriate icons from the available icons list
- Preserve the metadata section, updating edge_count, node_count, and timestamp as needed
- If no metadata exists, create it with inferred domain, current timestamp, and diagram_type from current_diagram

CRITICAL REQUIREMENTS:
- Return ONLY valid JSON in this EXACT format: {{"nodes": [...], "edges": [...], "metadata": {{...}}}}
- Each node MUST have: {{"id": "node_X", "type": "custom", "data": {{"label": "...", "image": "...", "description": "..."}}, "position": {{"x": 100, "y": 100}}}}
- Each edge MUST have: {{"id": "edge_X", "source": "node_X", "target": "node_Y", "type": "default", "label": "uses"}}
- When REMOVING nodes, also remove all edges connected to those nodes
- Preserve node IDs for existing nodes that aren't being removed
- Update metadata with current edge_count, node_count, timestamp, and preserve or infer domain and diagram_type
- DO NOT add any explanation, ONLY return the JSON

Return the complete modified diagram JSON now:
"""
        
        # Database diagram modification prompt
        self.database_modification_prompt = """
You are an expert database architect modifying database schema diagrams.

CONVERSATION HISTORY:
{conversation_history}

CURRENT DATABASE SCHEMA (JSON):
{current_diagram}

USER REQUEST: "{modification_request}"

MODIFICATION RULES:
1. ADD TABLE: If request says "add [table_name] table", create a new table node with appropriate fields
2. REMOVE TABLE: If request says "remove [table_name]" or "delete [table_name]", DELETE the table node and all related edges
3. ADD COLUMN: If request says "add [column_name] to [table_name]", add the field to that table's fields array
4. REMOVE COLUMN: If request says "remove [column_name] from [table_name]", remove that field from the table
5. ADD RELATIONSHIP: If request says "relate [table1] to [table2]", add a foreign key field and create an edge
6. MODIFY COLUMN: If request says "change [column_name] in [table_name]", update that field's properties
7. If a table already exists, UPDATE it instead of creating duplicate

CONTEXT INSTRUCTIONS:
- Use the conversation history to understand the schema evolution
- Maintain referential integrity when adding/removing foreign keys
- Follow proper database naming conventions (lowercase, snake_case for table IDs)
- When adding relationships, create both the foreign key field AND the edge
- When removing tables, also remove all foreign keys referencing that table
- Preserve the metadata section, updating edge_count, node_count, and timestamp
- Ensure all tables have at least an id field as primary key

DATABASE SCHEMA STRUCTURE:
Each table node MUST have:
{{
    "id": "table_name_lowercase",
    "type": "custom",
    "data": {{
        "label": "Table Name",
        "fields": [
            {{
                "name": "column_name",
                "type": "SQL_TYPE",
                "primaryKey": true/false,
                "foreignKey": true/false,
                "references": "table_id.column_name"  // Only if foreignKey is true
            }}
        ]
    }},
    "position": {{"x": number, "y": number}}
}}

Each relationship edge MUST have:
{{
    "id": "edge_table1_table2",
    "source": "parent_table_id",
    "target": "child_table_id",
    "type": "default",
    "label": "FK"
}}

CRITICAL REQUIREMENTS:
- Return ONLY valid JSON with "nodes", "edges", and "metadata" sections
- Every table must have at least a primary key field (usually "id")
- Foreign key fields must have "references" pointing to "table_id.column_name"
- When adding foreign keys, create the corresponding edge from parent to child
- When removing tables, remove all edges connected to that table
- Update metadata with current edge_count, node_count, timestamp, and diagram_type="db_diagram"
- DO NOT add any explanation, ONLY return the JSON

Return the complete modified database schema JSON now:
"""
    
    def apply_modification(
        self, 
        current_diagram: Dict, 
        modification_request: str,
        conversation_history: List[Dict] = None,
        available_icons: List[str] = None
    ) -> Dict:
        """
        Apply modifications to diagram using AI with full context.
        Automatically detects diagram type and uses appropriate modification strategy.
        """
        try:
            # Detect diagram type
            diagram_type = self._detect_diagram_type(current_diagram)
            logger.info(f"🔧 Starting {diagram_type} modification: '{modification_request}'")
            logger.info(f"📊 Current diagram has {len(current_diagram.get('nodes', []))} nodes")
            
            # Prepare conversation history for prompt
            conversation_history_str = json.dumps(conversation_history, indent=2) if conversation_history else "[]"
            
            # Select appropriate prompt template and prepare format args
            if diagram_type == "db_diagram":
                prompt_template = self.database_modification_prompt
                format_args = {
                    "conversation_history": conversation_history_str,
                    "current_diagram": json.dumps(current_diagram, indent=2),
                    "modification_request": modification_request
                }
            else:
                prompt_template = self.architecture_modification_prompt
                icons_str = json.dumps(available_icons) if available_icons else "[]"
                format_args = {
                    "conversation_history": conversation_history_str,
                    "current_diagram": json.dumps(current_diagram, indent=2),
                    "modification_request": modification_request,
                    "available_icons": icons_str
                }
            
            # Construct prompt with history
            prompt = prompt_template.format(**format_args)
            
            logger.info(f"🤖 Sending to Gemini AI ({diagram_type})...")
            
            # Generate with AI - retry up to 3 times
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.1,  # Low temperature for consistent output
                        )
                    )
                    response_text = response.text.strip()
                    
                    logger.info(f"📨 AI Response length: {len(response_text)} chars (attempt {attempt + 1}/{max_retries})")
                    
                    # Extract JSON
                    modified_diagram = self._extract_json_from_response(response_text)
                    
                    if not modified_diagram:
                        logger.warning(f"⚠️ Failed to extract valid JSON from AI response (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            logger.error("❌ All retry attempts failed to extract JSON")
                            raise ValueError("Failed to extract valid JSON from AI response after all retries")
                    
                    # Validate structure based on diagram type
                    if not self._validate_diagram_structure(modified_diagram, diagram_type):
                        logger.warning(f"⚠️ Invalid diagram structure from AI (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            logger.error("❌ All retry attempts failed validation")
                            raise ValueError("AI generated invalid diagram structure after all retries")
                    
                    # Ensure metadata is present and correct
                    if "metadata" not in modified_diagram:
                        modified_diagram["metadata"] = {
                            "domain": current_diagram.get("metadata", {}).get("domain", "unknown"),
                            "timestamp": datetime.utcnow().isoformat(),
                            "edge_count": len(modified_diagram.get("edges", [])),
                            "node_count": len(modified_diagram.get("nodes", [])),
                            "diagram_type": diagram_type
                        }
                    else:
                        # Update metadata counts and timestamp
                        modified_diagram["metadata"].update({
                            "edge_count": len(modified_diagram.get("edges", [])),
                            "node_count": len(modified_diagram.get("nodes", [])),
                            "timestamp": datetime.utcnow().isoformat(),
                            "diagram_type": diagram_type
                        })
                    
                    logger.info(f"✅ Successfully modified! New diagram has {len(modified_diagram.get('nodes', []))} nodes")
                    return modified_diagram
                    
                except Exception as retry_error:
                    logger.warning(f"⚠️ Attempt {attempt + 1} failed: {str(retry_error)}")
                    if attempt == max_retries - 1:
                        raise
            
            # If we get here, all retries failed
            raise ValueError("Failed to generate valid diagram after all retry attempts")
            
        except Exception as e:
            logger.error(f"❌ Modification error: {str(e)}", exc_info=True)
            # Return current diagram unchanged on error
            raise Exception(f"Failed to modify diagram: {str(e)}")
    
    def _detect_diagram_type(self, diagram: Dict) -> str:
        """Detect whether this is an architecture or database diagram"""
        # Check metadata first
        metadata = diagram.get("metadata", {})
        if "diagram_type" in metadata:
            return metadata["diagram_type"]
        
        # Check node structure
        nodes = diagram.get("nodes", [])
        if nodes:
            first_node = nodes[0]
            node_data = first_node.get("data", {})
            
            # Database diagrams have 'fields' in data
            if "fields" in node_data:
                return "db_diagram"
            # Architecture diagrams have 'image' and 'description'
            elif "image" in node_data or "description" in node_data:
                return "architecture"
        
        # Default to architecture
        return "architecture"
    
    def _extract_json_from_response(self, response_text: str) -> Dict:
        """Extract JSON from AI response (handles markdown code blocks)"""
        try:
            # Try direct parse
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{.*\})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                try:
                    json_str = match.group(1).strip()
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue
        
        logger.error("Failed to extract JSON from response")
        return None
    
    def _validate_diagram_structure(self, diagram: Dict, diagram_type: str) -> bool:
        """Validate diagram has required structure based on type"""
        if not isinstance(diagram, dict):
            logger.error("Diagram is not a dict")
            return False
        
        if "nodes" not in diagram or "edges" not in diagram:
            logger.error("Missing 'nodes' or 'edges' key")
            return False
        
        if not isinstance(diagram["nodes"], list):
            logger.error("'nodes' is not a list")
            return False
        
        if not isinstance(diagram["edges"], list):
            logger.error("'edges' is not a list")
            return False
        
        # Validate nodes based on diagram type
        for i, node in enumerate(diagram["nodes"]):
            if not isinstance(node, dict):
                logger.error(f"Node {i} is not a dict")
                return False
            
            if "id" not in node or "type" not in node or "data" not in node or "position" not in node:
                logger.error(f"Node {i} missing required fields")
                return False
            
            node_data = node["data"]
            if not isinstance(node_data, dict) or "label" not in node_data:
                logger.error(f"Node {i} missing 'label' in data")
                return False
            
            # Type-specific validation
            if diagram_type == "db_diagram":
                if "fields" not in node_data or not isinstance(node_data["fields"], list):
                    logger.error(f"Database node {i} missing 'fields' array")
                    return False
                
                # Validate fields structure
                for j, field in enumerate(node_data["fields"]):
                    if not isinstance(field, dict):
                        logger.error(f"Node {i} field {j} is not a dict")
                        return False
                    if "name" not in field or "type" not in field:
                        logger.error(f"Node {i} field {j} missing 'name' or 'type'")
                        return False
            elif diagram_type == "architecture":
                # Architecture nodes should have image (optional but common)
                pass
        
        # Validate edges
        for i, edge in enumerate(diagram["edges"]):
            if not isinstance(edge, dict):
                logger.error(f"Edge {i} is not a dict")
                return False
            
            if "id" not in edge or "source" not in edge or "target" not in edge or "type" not in edge:
                logger.error(f"Edge {i} missing required fields")
                return False
        
        logger.info(f"✅ Validation passed ({diagram_type}): {len(diagram['nodes'])} nodes, {len(diagram['edges'])} edges")
        return True
    
    def get_modification_summary(self, old_diagram: Dict, new_diagram: Dict) -> Dict:
        """Generate summary of what changed"""
        old_nodes = old_diagram.get("nodes", [])
        new_nodes = new_diagram.get("nodes", [])
        old_edges = old_diagram.get("edges", [])
        new_edges = new_diagram.get("edges", [])
        
        # Detect diagram type
        diagram_type = self._detect_diagram_type(new_diagram)
        
        # Track changes
        old_node_ids = {n["id"] for n in old_nodes}
        new_node_ids = {n["id"] for n in new_nodes}
        
        old_node_labels = {n["id"]: n.get("data", {}).get("label", "") for n in old_nodes}
        new_node_labels = {n["id"]: n.get("data", {}).get("label", "") for n in new_nodes}
        
        nodes_added = new_node_ids - old_node_ids
        nodes_removed = old_node_ids - new_node_ids
        
        # Check for updated nodes
        nodes_updated = []
        
        if diagram_type == "db_diagram":
            # For database diagrams, check for field changes
            old_node_map = {n["id"]: n for n in old_nodes}
            new_node_map = {n["id"]: n for n in new_nodes}
            
            for node_id in old_node_ids & new_node_ids:
                old_fields = old_node_map[node_id].get("data", {}).get("fields", [])
                new_fields = new_node_map[node_id].get("data", {}).get("fields", [])
                
                if old_fields != new_fields:
                    old_field_names = [f["name"] for f in old_fields]
                    new_field_names = [f["name"] for f in new_fields]
                    
                    added_fields = set(new_field_names) - set(old_field_names)
                    removed_fields = set(old_field_names) - set(new_field_names)
                    
                    nodes_updated.append({
                        "id": node_id,
                        "table": old_node_labels.get(node_id),
                        "fields_added": list(added_fields),
                        "fields_removed": list(removed_fields)
                    })
        else:
            # For architecture diagrams, check for label changes
            for node_id in old_node_ids & new_node_ids:
                if old_node_labels.get(node_id) != new_node_labels.get(node_id):
                    nodes_updated.append({
                        "id": node_id,
                        "old": old_node_labels.get(node_id),
                        "new": new_node_labels.get(node_id)
                    })
        
        removed_details = [
            {"id": node_id, "label": old_node_labels.get(node_id)}
            for node_id in nodes_removed
        ]
        
        added_details = [
            {"id": node_id, "label": new_node_labels.get(node_id)}
            for node_id in nodes_added
        ]
        
        summary = {
            "diagram_type": diagram_type,
            "nodes_added": len(nodes_added),
            "nodes_removed": len(nodes_removed),
            "nodes_updated": len(nodes_updated),
            "updated_details": nodes_updated,
            "removed_details": removed_details,
            "added_details": added_details,
            "edges_added": max(0, len(new_edges) - len(old_edges)),
            "edges_removed": max(0, len(old_edges) - len(new_edges)),
            "total_nodes": len(new_nodes),
            "total_edges": len(new_edges)
        }
        
        logger.info(f"📊 Modification Summary ({diagram_type}):")
        logger.info(f"   ➕ Added: {summary['nodes_added']} nodes")
        logger.info(f"   ➖ Removed: {summary['nodes_removed']} nodes")
        logger.info(f"   ✏️ Updated: {summary['nodes_updated']} nodes")
        
        if removed_details:
            logger.info(f"   Removed components:")
            for detail in removed_details:
                logger.info(f"      - {detail['label']}")
        
        return summary
from typing import Dict, List, Any, Optional
import json
import os
import logging
import re
from datetime import datetime

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import SystemMessage, HumanMessage
from app.core.simple_memory import ConversationBufferMemory

logger = logging.getLogger(__name__)

class DiagramModifier:
    """Service for intelligently modifying existing diagrams using AI with LangChain"""
    
    def __init__(self):
        # Initialize Gemini via LangChain
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")
        
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=api_key,
            temperature=0.1,
            convert_system_message_to_human=True
        )
        
        # Initialize memory for conversation context
        self.memory = ConversationBufferMemory(
            return_messages=True,
            memory_key="chat_history"
        )
        
        # Architecture diagram modification system prompt
        self.architecture_system_prompt = """You are an expert system architect modifying architecture diagrams.

MODIFICATION RULES:
1. ADD: If request says "add X", create a new node for X with appropriate icon from available icons
2. REMOVE: If request says "remove X" or "delete X", DELETE all nodes containing X in their label
3. UPDATE: If request says "change X to Y" or "make X use Y", UPDATE existing node X
4. CONNECT: If request says "connect X to Y", add an edge between them
5. If a component already exists, UPDATE it instead of creating duplicate

POSITION PRESERVATION RULES (CRITICAL):
- **NEVER CHANGE NODE OR EDGE POSITIONS** - This is absolutely critical
- For EXISTING nodes that are NOT being removed, copy their exact position from the current diagram: {{"x": same_x, "y": same_y}}
- For EXISTING edges, preserve them exactly as they are
- Only assign new positions to newly added nodes (use default positions like {{"x": 100, "y": 100}})
- When a node exists in both old and new versions, copy its position exactly without modification
- DO NOT move, reposition, or recalculate positions for any existing nodes or edges
- This ensures the diagram layout remains stable across modifications

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
- **PRESERVE EXACT POSITIONS for all existing nodes that are not being removed**
- Update metadata with current edge_count, node_count, timestamp, and preserve or infer domain and diagram_type
- DO NOT add any explanation, ONLY return the JSON"""
        
        # Database diagram modification system prompt
        self.database_system_prompt = """You are an expert database architect modifying database schema diagrams.

MODIFICATION RULES:
1. ADD TABLE: If request says "add [table_name] table", create a new table node with appropriate fields
2. REMOVE TABLE: If request says "remove [table_name]" or "delete [table_name]", DELETE the table node and all related edges
3. ADD COLUMN: If request says "add [column_name] to [table_name]", add the field to that table's fields array
4. REMOVE COLUMN: If request says "remove [column_name] from [table_name]", remove that field from the table
5. ADD RELATIONSHIP: If request says "relate [table1] to [table2]", add a foreign key field and create an edge
6. MODIFY COLUMN: If request says "change [column_name] in [table_name]", update that field's properties
7. If a table already exists, UPDATE it instead of creating duplicate

POSITION PRESERVATION RULES (CRITICAL):
- **NEVER CHANGE TABLE OR EDGE POSITIONS** - This is absolutely critical
- For EXISTING tables that are NOT being removed, copy their exact position from the current schema: {{"x": same_x, "y": same_y}}
- For EXISTING edges, preserve them exactly as they are
- Only assign new positions to newly added tables (use default positions like {{"x": 100, "y": 100}})
- When a table exists in both old and new versions, copy its position exactly without modification
- DO NOT move, reposition, or recalculate positions for any existing tables or edges
- This ensures the schema diagram layout remains stable across modifications

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
- **PRESERVE EXACT POSITIONS for all existing tables that are not being removed**
- Update metadata with current edge_count, node_count, timestamp, and diagram_type="db_diagram"
- DO NOT add any explanation, ONLY return the JSON"""
    
    def apply_modification(
        self, 
        current_diagram: Dict, 
        modification_request: str,
        conversation_history: Optional[List[Dict]] = None,
        available_icons: Optional[List[str]] = None
    ) -> Dict:
        """
        Apply modifications to diagram using AI with full context.
        Automatically detects diagram type and uses appropriate modification strategy.
        Preserves node positions for existing nodes when memory data exists.
        """
        try:
            # Detect diagram type
            diagram_type = self._detect_diagram_type(current_diagram)
            logger.info(f"🔧 Starting {diagram_type} modification: '{modification_request}'")
            logger.info(f"📊 Current diagram has {len(current_diagram.get('nodes', []))} nodes")
            
            # Build position map for existing nodes
            position_map = self._build_position_map(current_diagram)
            
            # Select appropriate system prompt
            if diagram_type == "db_diagram":
                system_prompt = self.database_system_prompt
            else:
                system_prompt = self.architecture_system_prompt
            
            # Build user message with context
            user_message = self._build_user_message(
                current_diagram=current_diagram,
                modification_request=modification_request,
                conversation_history=conversation_history,
                available_icons=available_icons,
                diagram_type=diagram_type
            )
            
            logger.info(f"🤖 Sending to Gemini AI via LangChain ({diagram_type})...")
            
            # Generate with AI - retry up to 3 times
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Create messages
                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_message)
                    ]
                    
                    # Get response from LLM
                    response = self.llm.invoke(messages)
                    response_text = response.content.strip()
                    
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
                    
                    # Restore positions for existing nodes if memory data exists
                    if conversation_history and position_map:
                        modified_diagram = self._restore_node_positions(modified_diagram, position_map)
                        logger.info(f"🔄 Restored positions for {len(position_map)} existing nodes")
                    
                    # Validate structure based on diagram type
                    if not self._validate_diagram_structure(modified_diagram, diagram_type):
                        logger.warning(f"⚠️ Invalid diagram structure from AI (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            logger.error("❌ All retry attempts failed validation")
                            raise ValueError("AI generated invalid diagram structure after all retries")
                    
                    # Ensure metadata is present and correct
                    modified_diagram = self._ensure_metadata(modified_diagram, current_diagram, diagram_type)
                    
                    # Save to memory
                    self.memory.save_context(
                        {"input": modification_request},
                        {"output": f"Modified {diagram_type}: {len(modified_diagram.get('nodes', []))} nodes"}
                    )
                    
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
            raise Exception(f"Failed to modify diagram: {str(e)}")
    
    def _build_position_map(self, diagram: Dict) -> Dict[str, Dict]:
        """Build a map of node IDs to their positions"""
        position_map = {}
        for node in diagram.get("nodes", []):
            node_id = node.get("id")
            position = node.get("position")
            if node_id and position:
                position_map[node_id] = position.copy()
        
        logger.info(f"📍 Built position map for {len(position_map)} nodes")
        return position_map
    
    def _restore_node_positions(self, modified_diagram: Dict, position_map: Dict[str, Dict]) -> Dict:
        """Restore positions for existing nodes from the position map"""
        restored_count = 0
        for node in modified_diagram.get("nodes", []):
            node_id = node.get("id")
            if node_id in position_map:
                node["position"] = position_map[node_id].copy()
                restored_count += 1
        
        logger.info(f"✅ Restored positions for {restored_count}/{len(position_map)} existing nodes")
        return modified_diagram
    
    def _build_user_message(
        self,
        current_diagram: Dict,
        modification_request: str,
        conversation_history: Optional[List[Dict]],
        available_icons: Optional[List[str]],
        diagram_type: str
    ) -> str:
        """Build the user message with all context"""
        
        # Format conversation history
        history_str = ""
        if conversation_history:
            history_str = "CONVERSATION HISTORY:\n"
            history_str += json.dumps(conversation_history, indent=2)
            history_str += "\n\n"
        
        # Format current diagram
        diagram_str = f"CURRENT {'DATABASE SCHEMA' if diagram_type == 'db_diagram' else 'DIAGRAM'} (JSON):\n"
        diagram_str += json.dumps(current_diagram, indent=2)
        diagram_str += "\n\n"
        
        # Format available icons (for architecture diagrams only)
        icons_str = ""
        if diagram_type == "architecture" and available_icons:
            icons_str = f"AVAILABLE ICONS: {json.dumps(available_icons)}\n\n"
        
        # Build complete message
        message = f"{history_str}{diagram_str}{icons_str}"
        message += f'USER REQUEST: "{modification_request}"\n\n'
        message += "Return the complete modified diagram JSON now:"
        
        return message
    
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
    
    def _extract_json_from_response(self, response_text: str) -> Optional[Dict]:
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
    
    def _ensure_metadata(self, modified_diagram: Dict, current_diagram: Dict, diagram_type: str) -> Dict:
        """Ensure metadata is present and up-to-date"""
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
        
        return modified_diagram
    
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
    
    def clear_memory(self):
        """Clear the conversation memory"""
        self.memory.clear()
        logger.info("🧹 Cleared conversation memory")

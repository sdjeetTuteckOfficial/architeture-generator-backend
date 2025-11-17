from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
import json
from datetime import datetime
from uuid import UUID
import logging
import jwt
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, AIMessage
import os
from app.database import get_db
from app.services import analyzer, diagram_generator
from app.services.modification_service import DiagramModifier
from app.services.thread_services import (
    create_thread, get_thread, create_conversation, 
    get_conversations, get_latest_conversation, update_conversation
)
from app.api.dependencies import get_current_user_from_websocket
from app.core import models
from constants.constants import AWS_AVAILABLE_IMAGES, AZURE_AVAILABLE_IMAGES, local_images

logger = logging.getLogger(__name__)
router = APIRouter()

# Available icons for architecture diagrams
AVAILABLE_ICONS = AWS_AVAILABLE_IMAGES + AZURE_AVAILABLE_IMAGES + local_images

# Service instances
analyzer_service = analyzer.ArchitectureAnalyzer()
diagram_gen_service = diagram_generator.DiagramGenerator()
modifier_service = DiagramModifier()

# ============= EXISTING ConnectionManager CLASS (UNCHANGED) =============
class ConnectionManager:
    """Manages WebSocket connections with LangChain memory per session"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        # Store memory per client/thread combination
        self.memories: Dict[str, ConversationBufferMemory] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected")
    
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected")
        
        # Clean up memories for this client
        keys_to_remove = [k for k in self.memories.keys() if k.startswith(f"{client_id}_")]
        for key in keys_to_remove:
            del self.memories[key]
    
    async def send_message(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)
    
    def get_memory(self, client_id: str, thread_id: str) -> ConversationBufferMemory:
        """Get or create memory for a specific client-thread combination"""
        memory_key = f"{client_id}_{thread_id}"
        
        if memory_key not in self.memories:
            self.memories[memory_key] = ConversationBufferMemory(
                return_messages=True,
                memory_key="chat_history",
                output_key="output"
            )
            logger.info(f"Created new memory for {memory_key}")
        
        return self.memories[memory_key]
    
    def clear_memory(self, client_id: str, thread_id: str):
        """Clear memory for a specific thread"""
        memory_key = f"{client_id}_{thread_id}"
        if memory_key in self.memories:
            self.memories[memory_key].clear()
            logger.info(f"Cleared memory for {memory_key}")

manager = ConnectionManager()

# ============= EXISTING HELPER FUNCTIONS (UNCHANGED) =============
async def load_conversation_memory_to_langchain(
    db: Session, 
    thread_id: UUID, 
    memory: ConversationBufferMemory,
    limit: int = 10
) -> List[Dict]:
    """
    Load previous conversations into LangChain memory with SUMMARIES only.
    Returns full diagram data separately for modification purposes.
    """
    conversations = get_conversations(db=db, thread_id=thread_id, skip=0, limit=limit)
    
    memory_data = []
    
    for conv in conversations:
        diagram_json = conv.diagram_json
        
        # Extract metadata summary (NOT the full diagram)
        if isinstance(diagram_json, dict):
            node_count = len(diagram_json.get("nodes", []))
            edge_count = len(diagram_json.get("edges", []))
            diagram_type = diagram_json.get("metadata", {}).get("diagram_type", "architecture")
            
            # Get component names for context
            component_names = [
                node.get("data", {}).get("label", "Unknown")
                for node in diagram_json.get("nodes", [])[:5]  # Only first 5
            ]
            
            # Create a lightweight summary for LangChain memory
            summary = f"Version {conv.version}: {diagram_type} with {node_count} components ({', '.join(component_names)}{'...' if node_count > 5 else ''})"
            
            # Add ONLY summary to LangChain memory (not full JSON!)
            memory.chat_memory.add_user_message(
                f"Diagram version {conv.version}"
            )
            memory.chat_memory.add_ai_message(summary)
            
        else:
            # Fallback for non-dict diagrams
            memory.chat_memory.add_user_message(f"Version {conv.version}")
            memory.chat_memory.add_ai_message(f"Generated diagram version {conv.version}")
        
        # Store FULL diagram data separately (not in LangChain memory)
        memory_data.append({
            "version": conv.version,
            "diagram_json": diagram_json,  # Full diagram for modifications
            "created_at": conv.created_at.isoformat(),
            "conversation_id": str(conv.conversation_id)
        })
    
    logger.info(f"Loaded {len(conversations)} conversation summaries into LangChain memory")
    logger.info(f"Stored {len(memory_data)} full diagrams separately for modifications")
    return sorted(memory_data, key=lambda x: x["version"])

async def build_context_from_memory(memory_data: List[Dict]) -> Dict:
    """Build enriched context from conversation history"""
    if not memory_data:
        return {}
    
    all_nodes = []
    all_edges = []
    technologies = set()
    
    for conv in memory_data:
        diagram = conv.get("diagram_json", {})
        if isinstance(diagram, dict):
            nodes = diagram.get("nodes", [])
            edges = diagram.get("edges", [])
            
            all_nodes.extend(nodes)
            all_edges.extend(edges)
            
            for node in nodes:
                if isinstance(node, dict):
                    label = node.get("data", {}).get("label", "")
                    technologies.add(label)
    
    return {
        "previous_versions": len(memory_data),
        "total_components": len(all_nodes),
        "total_connections": len(all_edges),
        "technologies_used": list(technologies),
        "evolution_history": [
            {
                "version": conv["version"],
                "component_count": len(conv.get("diagram_json", {}).get("nodes", [])),
                "created_at": conv["created_at"]
            }
            for conv in memory_data
        ]
    }
    
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
def get_latest_diagram(conversation_memory: List[Dict]) -> Dict:
    """Get the most recent diagram from memory"""
    if not conversation_memory:
        return {}
    return conversation_memory[-1].get("diagram_json", {})

def prepare_conversation_history_for_modifier(memory_data: List[Dict]) -> List[Dict]:
    """
    Convert memory data to format expected by modifier service.
    This includes ONLY the essential diagram structure for position preservation.
    """
    history = []
    for conv in memory_data:
        diagram = conv["diagram_json"]
        
        # Extract only what's needed: nodes with positions, edges, metadata
        essential_diagram = {
            "nodes": diagram.get("nodes", []),
            "edges": diagram.get("edges", []),
            "metadata": diagram.get("metadata", {})
        }
        
        history.append({
            "version": conv["version"],
            "diagram_json": essential_diagram,
            "timestamp": conv["created_at"]
        })
    
    return history

async def get_current_user(authorization: str = Header(None)):
    """
    Extract and validate user from Authorization header.
    Expected format: "Bearer <token>"
    Returns the user_id from the token payload.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )
    
    try:
        # Extract token from "Bearer <token>"
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication scheme"
            )
        
        # Decode JWT token
        payload = jwt.decode(
            token,
            SECRET_KEY,  # Your secret key
            algorithms=[ALGORITHM]  # Your algorithm (e.g., "HS256")
        )
        
        # Extract user_id from token payload
        # Adjust these field names based on your JWT structure
        user_id = payload.get("sub") or payload.get("user_id") or payload.get("id")
        
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token payload: user_id not found"
            )
        
        logger.info(f"🔐 Authenticated user: {user_id}")
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format"
        )


# ============= WEBSOCKET ENDPOINT WITH NEW DRAG MESSAGE TYPE =============
@router.websocket("/ws/architecture/{client_id}")
async def websocket_architecture_endpoint(
    websocket: WebSocket,
    client_id: str,
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time architecture diagram generation with LangChain memory"""
    
    await manager.connect(websocket, client_id)
    
    # Session state
    current_user = None
    current_thread_id = None
    current_memory: Optional[ConversationBufferMemory] = None
    current_version = 0
    current_analysis = None
    clarification_responses = {}
    awaiting_clarification = False
    conversation_memory = []  # Stores FULL diagrams for modifications
    
    try:
        await manager.send_message(client_id, {
            "type": "connected",
            "message": "✅ Connection established. Gunevo ArchitectX is now live, shaping ideas into intelligent architecture",
            "timestamp": datetime.now().isoformat()
        })
        
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            # Handle authentication
            if message_type == "auth":
                token = data.get("token")
                if not token:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Authentication token required"
                    })
                    continue
                
                current_user = await get_current_user_from_websocket(token, db)
                if not current_user:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Invalid authentication token"
                    })
                    continue
                
                await manager.send_message(client_id, {
                    "type": "authenticated",
                    "user_id": str(current_user.id),
                    "message": f"🔐 Authenticated as {current_user.email}"
                })
            
            # Handle thread creation
            elif message_type == "create_thread":
                if not current_user:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Please authenticate first"
                    })
                    continue
                
                thread_name = data.get("thread_name", f"Architecture Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                
                thread_data = models.ThreadCreate(
                    user_id=current_user.id,
                    thread_name=thread_name
                )
                
                thread = create_thread(db=db, thread_data=thread_data)
                current_thread_id = thread.thread_id
                current_version = 0
                conversation_memory = []
                
                # Initialize new memory for this thread
                current_memory = manager.get_memory(client_id, str(current_thread_id))
                
                await manager.send_message(client_id, {
                    "type": "thread_created",
                    "thread_id": str(current_thread_id),
                    "thread_name": thread_name,
                    "message": f"📝 New thread created: {thread_name}"
                })
            
            # Handle thread loading
            elif message_type == "load_thread":
                if not current_user:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Please authenticate first"
                    })
                    continue
                
                thread_id = UUID(data.get("thread_id"))
                thread = get_thread(db=db, thread_id=thread_id)
                
                if not thread or thread.user_id != current_user.id:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Thread not found or access denied"
                    })
                    continue
                
                # Get or create memory for this thread
                current_memory = manager.get_memory(client_id, str(thread_id))
                
                # Load conversation history: summaries to LangChain, full data to conversation_memory
                conversation_memory = await load_conversation_memory_to_langchain(
                    db, thread_id, current_memory, limit=20
                )
                memory_context = await build_context_from_memory(conversation_memory)
                
                current_thread_id = thread_id
                current_version = len(conversation_memory)
                
                # Send the latest diagram if exists
                latest_diagram = get_latest_diagram(conversation_memory) if conversation_memory else None
                
                await manager.send_message(client_id, {
                    "type": "thread_loaded",
                    "thread_id": str(thread_id),
                    "thread_name": thread.thread_name,
                    "version": current_version,
                    "memory_context": memory_context,
                    "conversations": conversation_memory,
                    "latest_diagram": latest_diagram,
                    "message": f"🔄 Loaded thread with {len(conversation_memory)} previous versions"
                })
            
            # ============= NEW: DRAG MESSAGE TYPE =============
            elif message_type == "drag":
                """
                Handle diagram updates from drag/drop operations.
                Updates the current version in-place (like REST API) without creating new version.
                """
                if not current_user or not current_thread_id:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Please create or load a thread first"
                    })
                    continue
                
                if not conversation_memory:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "No diagram exists yet. Use 'analyze' to create the first version."
                    })
                    continue
                
                diagram_json = data.get("diagram", {})
                
                logger.info(f"🖱️ Processing drag update for thread {current_thread_id}")
                logger.info(f"   - Nodes: {len(diagram_json.get('nodes', []))}")
                logger.info(f"   - Edges: {len(diagram_json.get('edges', []))}")
                
                try:
                    # Get latest conversation
                    latest_conversation = get_latest_conversation(db=db, thread_id=current_thread_id)
                    if not latest_conversation:
                        await manager.send_message(client_id, {
                            "type": "error",
                            "message": "No conversation found in this thread"
                        })
                        continue
                    
                    current_version_num = latest_conversation.version
                    
                    # Ensure metadata exists
                    if "metadata" not in diagram_json:
                        diagram_json["metadata"] = {}
                    
                    # Update metadata with counts and timestamp
                    diagram_json["metadata"].update({
                        "node_count": len(diagram_json.get("nodes", [])),
                        "edge_count": len(diagram_json.get("edges", [])),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    
                    # Update conversation in database (in-place, no new version)
                    latest_conversation.diagram_json = diagram_json
                    db.commit()
                    db.refresh(latest_conversation)
                    
                    logger.info(f"✅ Updated conversation {latest_conversation.conversation_id} via drag")
                    
                    # Update the conversation_memory list with the new diagram
                    if conversation_memory:
                        conversation_memory[-1]["diagram_json"] = diagram_json
                        conversation_memory[-1]["created_at"] = datetime.utcnow().isoformat()
                    
                    # Update ConversationBufferMemory
                    node_count = len(diagram_json.get("nodes", []))
                    edge_count = len(diagram_json.get("edges", []))
                    diagram_type = diagram_json.get("metadata", {}).get("diagram_type", "unknown")
                    
                    summary = (
                        f"Version {current_version_num} updated via drag: {node_count} nodes, "
                        f"{edge_count} edges. Type: {diagram_type}"
                    )
                    
                    if current_memory:
                        current_memory.chat_memory.add_user_message("Diagram updated via drag operation")
                        current_memory.chat_memory.add_ai_message(summary)
                        
                        messages = current_memory.chat_memory.messages
                        logger.info(f"   📝 Memory now has {len(messages)} total messages")
                    
                    # Send success response
                    await manager.send_message(client_id, {
                        "type": "diagram_drag_updated",
                        "version": current_version_num,
                        "diagram": diagram_json,
                        "message": f"✅ Diagram updated via drag in version {current_version_num}",
                        "metadata": {
                            "node_count": node_count,
                            "edge_count": edge_count,
                            "diagram_type": diagram_type
                        }
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Drag update error: {str(e)}", exc_info=True)
                    db.rollback()
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": f"Failed to update diagram: {str(e)}"
                    })
            
            # Handle modification requests (UNCHANGED - creates new version with AI)
            elif message_type == "modify":
                if not current_user or not current_thread_id or not current_memory:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Please create or load a thread first"
                    })
                    continue
                
                if not conversation_memory:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "No diagram exists yet. Use 'analyze' to create the first version."
                    })
                    continue
                
                modification_request = data.get("modification", "")
                
                await manager.send_message(client_id, {
                    "type": "processing",
                    "message": "🔧 Modifying your diagram with AI context..."
                })
                
                try:
                    # Get current diagram from conversation_memory (NOT from LangChain memory!)
                    current_diagram = get_latest_diagram(conversation_memory)
                    
                    logger.info(f"🔧 Starting modification request: '{modification_request}'")
                    logger.info(f"📊 Current diagram state:")
                    logger.info(f"   - Nodes: {len(current_diagram.get('nodes', []))}")
                    for node in current_diagram.get('nodes', []):
                        logger.info(f"      • {node['id']}: {node.get('data', {}).get('label', 'No label')}")
                    logger.info(f"   - Edges: {len(current_diagram.get('edges', []))}")
                    logger.info(f"📚 Conversation history: {len(conversation_memory)} versions")
                    
                    # Prepare history for modifier (with position preservation)
                    history_for_modifier = prepare_conversation_history_for_modifier(conversation_memory)
                    
                    # Apply modification with full diagram history (NOT LangChain memory!)
                    modified_diagram = modifier_service.apply_modification(
                        current_diagram, 
                        modification_request,
                        conversation_history=history_for_modifier,
                        available_icons=AVAILABLE_ICONS
                    )
                    
                    logger.info(f"📊 Modified diagram state:")
                    logger.info(f"   - Nodes: {len(modified_diagram.get('nodes', []))}")
                    for node in modified_diagram.get('nodes', []):
                        logger.info(f"      • {node['id']}: {node.get('data', {}).get('label', 'No label')}")
                    logger.info(f"   - Edges: {len(modified_diagram.get('edges', []))}")
                    
                    # Get modification summary
                    modification_summary = modifier_service.get_modification_summary(
                        current_diagram,
                        modified_diagram
                    )
                    
                    # Log the modification for debugging
                    logger.info(f"📝 Modification summary: {modification_summary}")
                    if modification_summary.get("updated_details"):
                        diagram_type = modification_summary.get("diagram_type", "architecture")
                        for detail in modification_summary["updated_details"]:
                            if diagram_type == "db_diagram":
                                # Database diagram updates
                                table_name = detail.get("table", detail.get("id"))
                                fields_added = detail.get("fields_added", [])
                                fields_removed = detail.get("fields_removed", [])
                                if fields_added:
                                    logger.info(f"   Table '{table_name}': Added fields {fields_added}")
                                if fields_removed:
                                    logger.info(f"   Table '{table_name}': Removed fields {fields_removed}")
                            else:
                                # Architecture diagram updates
                                logger.info(f"   Updated: '{detail.get('old', 'N/A')}' → '{detail.get('new', 'N/A')}'")
                    
                    # Validate metadata before saving
                    if "metadata" not in modified_diagram:
                        modified_diagram["metadata"] = {
                            "domain": current_diagram.get("metadata", {}).get("domain", "unknown"),
                            "timestamp": datetime.utcnow().isoformat(),
                            "edge_count": len(modified_diagram.get("edges", [])),
                            "node_count": len(modified_diagram.get("nodes", [])),
                            "diagram_type": current_diagram.get("metadata", {}).get("diagram_type", "architecture")
                        }
                    
                    # Save SUMMARY to LangChain memory (not full diagram!)
                    node_count = len(modified_diagram.get("nodes", []))
                    edge_count = len(modified_diagram.get("edges", []))
                    summary = f"Modified diagram: {modification_summary.get('nodes_added', 0)} added, {modification_summary.get('nodes_removed', 0)} removed. Total: {node_count} nodes, {edge_count} edges"
                    
                    current_memory.save_context(
                        {"input": modification_request},
                        {"output": summary}
                    )
                    
                    # Save modified version to database (NEW VERSION)
                    conversation_data = models.ConversationCreate(
                        thread_id=current_thread_id,
                        version=current_version,
                        diagram_json=modified_diagram
                    )
                    conversation = create_conversation(
                        db=db,
                        thread_id=current_thread_id,
                        conversation_data=conversation_data
                    )
                    
                    # Update conversation_memory with FULL diagram
                    conversation_memory.append({
                        "version": conversation.version,
                        "diagram_json": modified_diagram,
                        "created_at": conversation.created_at.isoformat(),
                        "conversation_id": str(conversation.conversation_id)
                    })
                    
                    current_version += 1
                    
                    # Rebuild memory context
                    memory_context = await build_context_from_memory(conversation_memory)
                    
                    await manager.send_message(client_id, {
                        "type": "diagram_modified",
                        "diagram": modified_diagram,
                        "version": current_version - 1,
                        "modification": modification_request,
                        "modification_summary": modification_summary,
                        "memory_context": memory_context,
                        "metadata": {
                            "node_count": len(modified_diagram.get("nodes", [])),
                            "edge_count": len(modified_diagram.get("edges", [])),
                            "is_modification": True
                        },
                        "message": f"✅ Diagram modified! Version {current_version - 1}"
                    })
                
                except Exception as e:
                    logger.error(f"Modification error: {str(e)}", exc_info=True)
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": f"Failed to modify diagram: {str(e)}"
                    })
            
            # Handle analysis request (only for first version)
            elif message_type == "analyze":
                if not current_user:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Please authenticate first"
                    })
                    continue
                
                description = data.get("description", "")
                diagram_type = data.get("diagram_type", "architecture")
                
                await manager.send_message(client_id, {
                    "type": "processing",
                    "message": "🔍 Analyzing your project..."
                })
                
                context = analyzer_service.analyze_context(description)
                completeness = analyzer_service.calculate_completeness(context, description)
                needs_clarification = completeness < 0.6
                
                current_analysis = {
                    "original_description": description,
                    "extracted_context": context,
                    "completeness_score": completeness,
                    "needs_clarification": needs_clarification,
                    "diagram_type": diagram_type
                }
                
                if needs_clarification:
                    questions = analyzer_service.generate_questions(context, completeness)
                    current_analysis["clarification_questions"] = questions
                    awaiting_clarification = True
                    clarification_responses = {}
                    
                    await manager.send_message(client_id, {
                        "type": "clarification_needed",
                        "analysis": current_analysis,
                        "questions": questions,
                        "message": f"🎯 I need some clarifications (Completeness: {int(completeness*100)}%)"
                    })
                else:
                    await manager.send_message(client_id, {
                        "type": "generating",
                        "message": "🎨 Generating your diagram..."
                    })
                    
                    if diagram_type == "db_diagram":
                        diagram_data = diagram_gen_service.generate_database_diagram(
                            description, context, {}
                        )
                    else:
                        diagram_data = diagram_gen_service.generate_architecture_diagram(
                            description, context, {}
                        )
                    
                    # Ensure metadata is present
                    if "metadata" not in diagram_data:
                        diagram_data["metadata"] = {
                            "domain": context.get("domain", "unknown"),
                            "timestamp": datetime.utcnow().isoformat(),
                            "edge_count": len(diagram_data.get("edges", [])),
                            "node_count": len(diagram_data.get("nodes", [])),
                            "diagram_type": diagram_type
                        }
                    
                    # Ensure thread exists
                    if not current_thread_id:
                        thread_name = f"Architecture Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        thread_data = models.ThreadCreate(
                            user_id=current_user.id,
                            thread_name=thread_name
                        )
                        thread = create_thread(db=db, thread_data=thread_data)
                        current_thread_id = thread.thread_id
                        current_version = 0
                        
                        # Initialize memory for new thread
                        current_memory = manager.get_memory(client_id, str(current_thread_id))
                    
                    # Save SUMMARY to LangChain memory (not full diagram!)
                    node_count = len(diagram_data.get("nodes", []))
                    edge_count = len(diagram_data.get("edges", []))
                    summary = f"Generated {diagram_type} diagram with {node_count} components and {edge_count} connections"
                    
                    if current_memory:
                        current_memory.save_context(
                            {"input": description},
                            {"output": summary}
                        )
                    
                    conversation_data = models.ConversationCreate(
                        thread_id=current_thread_id,
                        version=current_version,
                        diagram_json=diagram_data
                    )
                    conversation = create_conversation(
                        db=db,
                        thread_id=current_thread_id,
                        conversation_data=conversation_data
                    )
                    
                    # Update conversation_memory with FULL diagram
                    conversation_memory.append({
                        "version": conversation.version,
                        "diagram_json": diagram_data,
                        "created_at": conversation.created_at.isoformat(),
                        "conversation_id": str(conversation.conversation_id)
                    })
                    
                    current_version += 1
                    
                    # Build memory context
                    memory_context = await build_context_from_memory(conversation_memory)
                    
                    await manager.send_message(client_id, {
                        "type": "diagram_generated",
                        "diagram": diagram_data,
                        "version": current_version - 1,
                        "thread_id": str(current_thread_id),
                        "memory_context": memory_context,
                        "metadata": {
                            "node_count": len(diagram_data.get("nodes", [])),
                            "edge_count": len(diagram_data.get("edges", [])),
                            "diagram_type": diagram_type
                        },
                        "message": f"✅ Diagram generated! Version {current_version - 1}"
                    })
            
            # Handle clarification response
            elif message_type == "clarification_response":
                if not awaiting_clarification or not current_analysis:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "No clarification pending"
                    })
                    continue
                
                response = data.get("response", "")
                question_index = len(clarification_responses)
                clarification_responses[f"question_{question_index}"] = response
                
                questions = current_analysis.get("clarification_questions", [])
                
                if len(clarification_responses) >= len(questions):
                    awaiting_clarification = False
                    
                    await manager.send_message(client_id, {
                        "type": "generating",
                        "message": "🎨 All clarifications received! Generating..."
                    })
                    
                    diagram_type = current_analysis.get("diagram_type", "architecture")
                    
                    if diagram_type == "db_diagram":
                        diagram_data = diagram_gen_service.generate_database_diagram(
                            current_analysis["original_description"],
                            current_analysis["extracted_context"],
                            clarification_responses
                        )
                    else:
                        diagram_data = diagram_gen_service.generate_architecture_diagram(
                            current_analysis["original_description"],
                            current_analysis["extracted_context"],
                            clarification_responses
                        )
                    
                    # Ensure metadata is present
                    if "metadata" not in diagram_data:
                        diagram_data["metadata"] = {
                            "domain": current_analysis["extracted_context"].get("domain", "unknown"),
                            "timestamp": datetime.utcnow().isoformat(),
                            "edge_count": len(diagram_data.get("edges", [])),
                            "node_count": len(diagram_data.get("nodes", [])),
                            "diagram_type": diagram_type
                        }
                    
                    # Ensure thread exists
                    if not current_thread_id:
                        t_name = "Architecture" if diagram_type == "architecture" else "Database"
                        thread_name = f"{t_name} Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        thread_data = models.ThreadCreate(
                            user_id=current_user.id,
                            thread_name=thread_name
                        )
                        
                        thread = create_thread(db=db, thread_data=thread_data)
                        current_thread_id = thread.thread_id
                        current_version = 0
                        
                        # Initialize memory for new thread
                        current_memory = manager.get_memory(client_id, str(current_thread_id))
                    
                    # Save SUMMARY to LangChain memory (not full diagram!)
                    node_count = len(diagram_data.get("nodes", []))
                    edge_count = len(diagram_data.get("edges", []))
                    summary = f"Generated {diagram_type} with {node_count} components after clarifications"
                    
                    if current_memory:
                        current_memory.save_context(
                            {"input": f"{current_analysis['original_description']} (with clarifications)"},
                            {"output": summary}
                        )
                    
                    conversation_data = models.ConversationCreate(
                        thread_id=current_thread_id,
                        version=current_version,
                        diagram_json=diagram_data
                    )
                    conversation = create_conversation(
                        db=db,
                        thread_id=current_thread_id,
                        conversation_data=conversation_data
                    )
                    
                    # Update conversation_memory with FULL diagram
                    conversation_memory.append({
                        "version": conversation.version,
                        "diagram_json": diagram_data,
                        "created_at": conversation.created_at.isoformat(),
                        "conversation_id": str(conversation.conversation_id)
                    })
                    
                    current_version += 1
                    
                    memory_context = await build_context_from_memory(conversation_memory)
                    
                    await manager.send_message(client_id, {
                        "type": "diagram_generated",
                        "diagram": diagram_data,
                        "version": current_version - 1,
                        "thread_id": str(current_thread_id),
                        "memory_context": memory_context,
                        "metadata": {
                            "node_count": len(diagram_data.get("nodes", [])),
                            "edge_count": len(diagram_data.get("edges", [])),
                            "diagram_type": diagram_type
                        },
                        "message": f"✅ Diagram generated! Version {current_version - 1}"
                    })
                else:
                    next_question = questions[len(clarification_responses)]
                    await manager.send_message(client_id, {
                        "type": "next_question",
                        "question": next_question,
                        "progress": {
                            "current": len(clarification_responses) + 1,
                            "total": len(questions)
                        },
                        "message": f"💡 Question {len(clarification_responses) + 1}/{len(questions)}"
                    })
            
            elif message_type == "ping":
                await manager.send_message(client_id, {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {str(e)}", exc_info=True)
        try:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"Server error: {str(e)}"
            })
        except:
            pass
        manager.disconnect(client_id)
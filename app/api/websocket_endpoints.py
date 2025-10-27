from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, List, Any
import json
from datetime import datetime
from uuid import UUID
import logging

from app.database import get_db, SessionLocal
from app.services import analyzer, diagram_generator
from app.services.modification_service import DiagramModifier
from app.services.thread_services import (
    create_thread, get_thread, create_conversation, 
    get_conversations
)
from app.api.dependencies import get_current_user_from_websocket
from app.core import models

logger = logging.getLogger(__name__)
router = APIRouter()

# Service instances
analyzer_service = analyzer.ArchitectureAnalyzer()
diagram_gen_service = diagram_generator.DiagramGenerator()
modifier_service = DiagramModifier()

class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected")
    
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected")
    
    async def send_message(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

manager = ConnectionManager()

async def load_conversation_memory(db: SessionLocal, thread_id: UUID, limit: int = 10) -> List[Dict]:
    """Load previous conversations for context"""
    conversations = get_conversations(db=db, thread_id=thread_id, skip=0, limit=limit)
    
    memory = []
    for conv in conversations:
        memory.append({
            "version": conv.version,
            "diagram_json": conv.diagram_json,
            "created_at": conv.created_at.isoformat(),
            "conversation_id": str(conv.conversation_id)
        })
    
    return sorted(memory, key=lambda x: x["version"])

async def build_context_from_memory(memory: List[Dict]) -> Dict:
    """Build enriched context from conversation history"""
    if not memory:
        return {}
    
    all_nodes = []
    all_edges = []
    technologies = set()
    
    for conv in memory:
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
        "previous_versions": len(memory),
        "total_components": len(all_nodes),
        "total_connections": len(all_edges),
        "technologies_used": list(technologies),
        "evolution_history": [
            {
                "version": conv["version"],
                "component_count": len(conv.get("diagram_json", {}).get("nodes", [])),
                "created_at": conv["created_at"]
            }
            for conv in memory
        ]
    }

def get_latest_diagram(conversation_memory: List[Dict]) -> Dict:
    """Get the most recent diagram from memory"""
    if not conversation_memory:
        return {}
    return conversation_memory[-1].get("diagram_json", {})

@router.websocket("/ws/architecture/{client_id}")
async def websocket_architecture_endpoint(
    websocket: WebSocket,
    client_id: str,
    db: SessionLocal = Depends(get_db)
):
    """WebSocket endpoint for real-time architecture diagram generation with memory"""
    
    await manager.connect(websocket, client_id)
    
    # Session state
    current_user = None
    current_thread_id = None
    current_version = 0
    current_analysis = None
    clarification_responses = {}
    awaiting_clarification = False
    conversation_memory = []
    
    try:
        await manager.send_message(client_id, {
            "type": "connected",
            "message": "✨ WebSocket connected! I'm your AI architect with memory.",
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
                
                conversation_memory = await load_conversation_memory(db, thread_id, limit=20)
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
            
            # Handle modification requests
            elif message_type == "modify":
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
                
                modification_request = data.get("modification", "")
                
                await manager.send_message(client_id, {
                    "type": "processing",
                    "message": "🔧 Modifying your diagram with AI context..."
                })
                
                try:
                    # Get current diagram
                    current_diagram = get_latest_diagram(conversation_memory)
                    
                    logger.info(f"🔧 Starting modification request: '{modification_request}'")
                    logger.info(f"📊 Current diagram state:")
                    logger.info(f"   - Nodes: {len(current_diagram.get('nodes', []))}")
                    for node in current_diagram.get('nodes', []):
                        logger.info(f"      • {node['id']}: {node.get('data', {}).get('label', 'No label')}")
                    logger.info(f"   - Edges: {len(current_diagram.get('edges', []))}")
                    logger.info(f"📚 Conversation history: {len(conversation_memory)} versions")
                    
                    # Apply modification
                    modified_diagram = modifier_service.apply_modification(
                        current_diagram, 
                        modification_request,
                        conversation_history=conversation_memory
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
                        for detail in modification_summary["updated_details"]:
                            logger.info(f"   Updated: '{detail['old']}' → '{detail['new']}'")
                    
                    # Validate metadata before saving
                    if "metadata" not in modified_diagram:
                        modified_diagram["metadata"] = {
                            "domain": current_diagram.get("metadata", {}).get("domain", "unknown"),
                            "timestamp": datetime.utcnow().isoformat(),
                            "edge_count": len(modified_diagram.get("edges", [])),
                            "node_count": len(modified_diagram.get("nodes", [])),
                            "diagram_type": current_diagram.get("metadata", {}).get("diagram_type", "architecture")
                        }
                    
                    # Save modified version
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
                    
                    # Update memory
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
                    
                    # Update memory
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
                        thread_name = f"Architecture Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        thread_data = models.ThreadCreate(
                            user_id=current_user.id,
                            thread_name=thread_name
                        )
                        thread = create_thread(db=db, thread_data=thread_data)
                        current_thread_id = thread.thread_id
                        current_version = 0
                    
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
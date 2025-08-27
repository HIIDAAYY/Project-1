import logging
import operator
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver  # Untuk persistence
from tools import order_tool, product_tool, faq_tool, llm, clarify_query  # Tambah clarify_query dari tools

# Gabungkan semua alat yang tersedia (tambah clarify kalau perlu)
tools = [product_tool, order_tool, faq_tool, clarify_query]  # Tambah clarify tool
# Ikat alat ke LLM
llm_with_tools = llm.bind_tools(tools)

# State dengan tambahan flag untuk ambiguous/reflect
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    user_number: str
    is_ambiguous: bool  # Flag kalau query perlu clarify
    needs_reflection: bool  # Flag kalau output tool perlu review

# Node utama yang memanggil LLM untuk reason
def call_model_node(state: AgentState):
    """Memanggil LLM untuk reason dan decide action."""
    response = llm_with_tools.invoke(state['messages'])
    return {
        "messages": [response],
        "is_ambiguous": "ambiguous" in response.content.lower(),  # Detect kalau LLM bilang ambigu
        "needs_reflection": False  # Default, set true kalau tool dipanggil
    }

# Node untuk jalankan tool
tool_node = ToolNode(tools)

# Node baru untuk clarify query ambigu
def clarify_node(state: AgentState):
    """Handle query ambigu: LLM tanya klarifikasi atau rewrite."""
    clarify_prompt = "Query user ambigu. Tanya klarifikasi santai atau rewrite ke format standard berdasarkan riwayat."
    response = llm.invoke([HumanMessage(content=clarify_prompt)] + state['messages'][-3:])  # Pakai history terakhir
    return {
        "messages": [AIMessage(content=response.content)],  # Balas tanya seperti "Produk mana nih, Kak?"
        "is_ambiguous": False  # Reset flag
    }

# Node baru untuk self-reflection setelah tool
def reflect_node(state: AgentState):
    """Review output tool: LLM decide kalau perlu retry atau final."""
    reflect_prompt = "Review output tool terakhir. Kalau ambigu atau salah, decide next step (retry tool atau end)."
    response = llm.invoke([HumanMessage(content=reflect_prompt)] + state['messages'][-2:])  # Review tool result
    return {
        "messages": [AIMessage(content=response.content)],
        "needs_reflection": False  # Reset
    }

# Kondisional untuk decide alur
def should_continue_node(state: AgentState):
    last_message = state['messages'][-1]
    if state['is_ambiguous']:
        return "clarify"  # Ke clarify kalau ambigu
    if last_message.tool_calls:
        return "action"  # Ke tool
    if state['needs_reflection']:
        return "reflect"  # Ke reflect setelah tool
    return "end"  # Selesai

# Membangun graph
graph = StateGraph(AgentState)

# Tambah node
graph.add_node("agent", call_model_node)
graph.add_node("action", tool_node)
graph.add_node("clarify", clarify_node)  # Node baru
graph.add_node("reflect", reflect_node)  # Node baru

# Entry point
graph.set_entry_point("agent")

# Conditional edges
graph.add_conditional_edges(
    "agent",
    should_continue_node,
    {
        "clarify": "clarify",
        "action": "action",
        "reflect": "reflect",
        "end": END,
    },
)

# Edges lain
graph.add_edge("action", "reflect")  # Setelah tool, selalu reflect
graph.add_edge("clarify", "agent")  # Loop kembali ke agent setelah clarify
graph.add_edge("reflect", "agent")  # Loop kalau perlu retry dari reflect

# Compile dengan MemorySaver
memory_saver = MemorySaver()
compiled_graph = graph.compile(checkpointer=memory_saver)
logging.basicConfig(level=logging.INFO)
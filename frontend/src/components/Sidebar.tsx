import { BookOpenText, GitBranch, MessageSquare, Plus, Scale, X } from 'lucide-react'
import type { Conversation } from '../types'

export default function Sidebar({open,items,active,onNew,onSelect,onClose,onKnowledge,onWorkflow}:{open:boolean;items:Conversation[];active?:string;onNew:()=>void;onSelect:(id:string)=>void;onClose:()=>void;onKnowledge:()=>void;onWorkflow:()=>void}) {
  return <aside className={`sidebar ${open?'open':''}`} aria-label="Conversation history">
    <div className="brand"><span><Scale size={22}/> Nyay Saathi</span><button className="mobile-close" onClick={onClose} aria-label="Close sidebar"><X/></button></div>
    <button className="new-chat" onClick={onNew}><Plus size={18}/> New chat</button>
    <div className="history-label">Your cases</div>
    <nav>{items.map(c=><button key={c.id} className={`history-item ${active===c.id?'active':''}`} onClick={()=>onSelect(c.id)}>
      <MessageSquare size={16}/><span><b>{c.title}</b><small>{c.last_message||'No messages yet'}</small></span>
    </button>)}</nav>
    <div className="sidebar-tools" aria-label="About this assistant">
      <button onClick={onKnowledge}><BookOpenText size={16}/><span><b>Knowledge Base</b><small>Official documents and indexed passages</small></span></button>
      <button onClick={onWorkflow}><GitBranch size={16}/><span><b>Agent Workflow</b><small>Input, decisions, checks, and output</small></span></button>
    </div>
    <div className="sidebar-note">Chats stay available in this browser. Export anything you want to keep.</div>
  </aside>
}

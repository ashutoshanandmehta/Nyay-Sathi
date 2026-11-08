import {
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Scale,
  Settings,
  Trash2,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Conversation, StreamEvent } from '../types'
import AgentFlowWidget from './AgentFlowWidget'

export default function Sidebar({
  open,
  items,
  active,
  onNew,
  onSelect,
  onClose,
  onKnowledge,
  onWorkflow,
  onRename,
  onDelete,
  onDevspace,
  onSettings,
  isStreaming = false,
  streamEvents = [],
}: {
  open: boolean
  items: Conversation[]
  active?: string
  onNew: () => void
  onSelect: (id: string) => void
  onClose: () => void
  onKnowledge: () => void
  onWorkflow: () => void
  onRename?: (id: string, title: string) => void | Promise<void>
  onDelete?: (id: string) => void | Promise<void>
  onDevspace?: () => void
  onSettings?: (tab?: 'knowledge' | 'workflow' | 'devspace') => void
  isStreaming?: boolean
  streamEvents?: StreamEvent[]
}) {
  const [menuFor, setMenuFor] = useState<string | null>(null),
    [editing, setEditing] = useState<string | null>(null),
    [draft, setDraft] = useState('')
  // Guards against the blur that follows Enter/Escape saving a second time.
  const editingRef = useRef<string | null>(null)

  useEffect(() => {
    if (!menuFor) return
    const onPointer = (e: MouseEvent) => {
      if (!(e.target as Element).closest?.('.history-item-row.menu-open')) setMenuFor(null)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuFor(null)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuFor])

  function startRename(c: Conversation) {
    setMenuFor(null)
    editingRef.current = c.id
    setEditing(c.id)
    setDraft(c.title)
  }

  function finishRename(id: string, save: boolean) {
    if (editingRef.current !== id) return
    editingRef.current = null
    setEditing(null)
    const title = draft.trim()
    if (save && title && title !== items.find(c => c.id === id)?.title) void onRename?.(id, title)
  }

  const handleOpenSettings = () => {
    if (onSettings) {
      onSettings('devspace')
    } else {
      onKnowledge()
    }
  }

  return (
    <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Conversation history">
      <div className="brand">
        <span>
          <Scale size={22} /> Nyay Saathi
        </span>
        <button className="mobile-close" onClick={onClose} aria-label="Close sidebar">
          <X />
        </button>
      </div>
      <button className="new-chat" onClick={onNew}>
        <Plus size={18} /> New chat
      </button>

      <div className="history-label">Your cases</div>
      <nav>
        {items.map(c => (
          <div key={c.id} className={`history-item-row ${menuFor === c.id ? 'menu-open' : ''}`}>
            {editing === c.id ? (
              <div className="history-item active editing">
                <MessageSquare size={16} />
                <input
                  aria-label="Chat title"
                  value={draft}
                  maxLength={100}
                  autoFocus
                  onChange={e => setDraft(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      finishRename(c.id, true)
                    } else if (e.key === 'Escape') finishRename(c.id, false)
                  }}
                  onBlur={() => finishRename(c.id, true)}
                />
              </div>
            ) : (
              <button
                className={`history-item ${active === c.id ? 'active' : ''}`}
                onClick={() => onSelect(c.id)}
              >
                <MessageSquare size={16} />
                <span>
                  <b>{c.title}</b>
                  <small>{c.last_message || 'No messages yet'}</small>
                </span>
              </button>
            )}
            {editing !== c.id && (onRename || onDelete) && (
              <button
                className="history-actions"
                aria-label={`Chat actions for ${c.title}`}
                aria-haspopup="menu"
                aria-expanded={menuFor === c.id}
                onClick={e => {
                  e.stopPropagation()
                  setMenuFor(menuFor === c.id ? null : c.id)
                }}
              >
                <MoreHorizontal size={15} />
              </button>
            )}
            {menuFor === c.id && (
              <div className="dropdown history-menu" role="menu">
                {onRename && (
                  <button role="menuitem" onClick={() => startRename(c)}>
                    <Pencil /> Rename
                  </button>
                )}
                {onDelete && (
                  <button
                    role="menuitem"
                    className="danger"
                    onClick={() => {
                      setMenuFor(null)
                      void onDelete(c.id)
                    }}
                  >
                    <Trash2 /> Delete
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* Live Synchronized Agent Flow Animation in Vacated Vertical Space */}
      <AgentFlowWidget
        isStreaming={isStreaming}
        events={streamEvents}
        onOpenWorkflow={onWorkflow}
      />

      {/* Full-width Settings Button & Footer */}
      <div className="sidebar-footer">
        <button
          className="sidebar-settings-button"
          onClick={handleOpenSettings}
          aria-label="Settings"
          title="Open Settings (DevSpace, Agent Workflow, Knowledge Base)"
        >
          <Settings size={16} />
          <span>Settings</span>
        </button>
      </div>

      <div className="sidebar-note">Chats stay available in this browser. Export anything you want to keep.</div>
    </aside>
  )
}

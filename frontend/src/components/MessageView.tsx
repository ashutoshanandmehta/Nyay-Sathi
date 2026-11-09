import {
  BookOpen,
  Check,
  ClipboardList,
  Copy,
  FileText,
  GitFork,
  ListChecks,
  RotateCcw,
  Route,
  Scale,
  Siren,
  Sparkles,
  Volume2,
} from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BLOCK_TYPE_ICONS, GROUNDING_ICONS } from '../icons'
import type { Message, ResolutionBlock, Source } from '../types'

// The backend writes in-text citations as "[1](#cite-1)", numbered to match source.citation_number.
const CITE_HREF=/^#cite-(\d+)$/
const CITE_MARKER=/\[(\d+)\]\(#cite-\d+\)/g

export function enhanceListReadability(text: string): string {
  if (!text) return ''
  let inCode = false
  return text
    .split('\n')
    .map(line => {
      if (line.trim().startsWith('```')) {
        inCode = !inCode
        return line
      }
      if (inCode) return line

      // "Step 1:" or "Step 1." -> "1. "
      const stepMatch = line.match(/^(\s*)Step\s+(\d+)[:.]\s*(.*)$/i)
      if (stepMatch) {
        return `${stepMatch[1]}${stepMatch[2]}. ${stepMatch[3]}`
      }
      // "1)" or "2)" -> "1. "
      const parenMatch = line.match(/^(\s*)(\d+)\)\s*(.*)$/)
      if (parenMatch) {
        return `${parenMatch[1]}${parenMatch[2]}. ${parenMatch[3]}`
      }
      // Unicode bullet characters •, ●, ▪, ⁃, ‣ -> "- "
      const bulletMatch = line.match(/^(\s*)[•●▪⁃‣]\s*(.*)$/)
      if (bulletMatch) {
        return `${bulletMatch[1]}- ${bulletMatch[2]}`
      }
      return line
    })
    .join('\n')
}

export function formatInlineCitations(text: string): string {
  if (!text) return ''
  // Strip raw parenthetical source descriptions like "(Bihar government guidance on mutation, Page 2.)"
  // that precede clickable citation chips [N](#cite-N)
  return text.replace(
    /(?<!\])\s*\((?!\s*#cite-)([^)\n]{3,100}?)\)\s*(?=\[\d+\]\(#cite-\d+\))/g,
    ' '
  )
}

function plainCitations(content:string, sources?:Source[]) {
  const text=content.replace(CITE_MARKER,'[$1]')
  const numbered=(sources||[]).filter(s=>s.citation_number)
  if(!numbered.length) return text
  return `${text}\n\nSources:\n${numbered.map(s=>`[${s.citation_number}] ${s.title} — ${s.locator}${s.canonical_url?` — ${s.canonical_url}`:''}`).join('\n')}`
}

function citationComponents(sources:Source[]|undefined, onSources:(s:Source[], focus?:number)=>void):Components {
  return {
    a: ({href, children}) => {
      const match=CITE_HREF.exec(href||'')
      if(!match) return <a href={href} target="_blank" rel="noreferrer">{children}</a>
      const number=Number(match[1]), source=sources?.find(s=>s.citation_number===number)
      if(!source) return <span className="cite-chip cite-chip-missing">{number}</span>
      return <button type="button" className="cite-chip" title={`${source.title} — ${source.locator}`} aria-label={`Source ${number}: ${source.title}`} onClick={()=>onSources(sources!, number)}>{number}</button>
    },
    h2: ({children}) => <h2 className="prose-h2">{children}</h2>,
    h3: ({children}) => {
      const text = String(children || '')
      const isLawyer = /lawyer|advocate|vakil|वकील/i.test(text)
      const isEscalation = /fails|escalat|court|police|dispute|doesn't work|agar isse baat na bane|बात न बने/i.test(text)
      const isAction = /action|step|do this|now|precaution|today|aaj aap|आज आप/i.test(text)
      const isRoute = /route|recommen|path|procedure|suggest|salah|सलाह/i.test(text)
      const isEvidence = /evidence|checklist|document|proof|record|keep these ready|ready rakhein|तैयार रखें/i.test(text)
      const Icon = isLawyer ? Scale : isEscalation ? GitFork : isAction ? ListChecks : isRoute ? Route : isEvidence ? ClipboardList : null
      return (
        <h3 className="prose-h3">
          {Icon && <Icon size={16} className="prose-heading-icon" aria-hidden="true" />}
          <span>{children}</span>
        </h3>
      )
    },
    ol: ({children}) => <ol className="prose-ordered-list">{children}</ol>,
    ul: ({children}) => <ul className="prose-unordered-list">{children}</ul>,
    li: ({children}) => <li className="prose-list-item">{children}</li>,
    hr: () => <hr className="markdown-divider" />,
    blockquote: ({children}) => <blockquote className="markdown-quote">{children}</blockquote>,
  }
}

function BlockCard({
  block,
  onOpenCase,
  sources,
  onSources,
}:{
  block:ResolutionBlock
  onOpenCase?:()=>void
  sources?:Source[]
  onSources:(s:Source[], focus?:number)=>void
}) {
  const [copiedDoc, setCopiedDoc] = useState(false)
  async function copyDoc() {
    await navigator.clipboard.writeText(block.content)
    setCopiedDoc(true)
    setTimeout(() => setCopiedDoc(false), 1200)
  }
  const useList = block.items && block.items.length > 1
  const blockMeta = BLOCK_TYPE_ICONS[block.block_type] || BLOCK_TYPE_ICONS.direct_answer
  const BlockIcon = blockMeta.icon
  const groundingMeta = GROUNDING_ICONS[block.grounding] || GROUNDING_ICONS.verified_legal_source
  const GroundingIcon = groundingMeta.icon

  return (
    <section className={`res-block res-block-${block.block_type}`} data-block-type={block.block_type}>
      <div className="res-block-head">
        <div className="res-block-type-chip" style={{ color: blockMeta.colorVar }}>
          <BlockIcon size={16} aria-hidden="true" />
          <strong>{block.title}</strong>
        </div>
        <span className={`grounding-pill grounding-${block.grounding}`} title={groundingMeta.label}>
          <GroundingIcon size={12} aria-hidden="true" />
          <span>{groundingMeta.label}</span>
        </span>
      </div>
      {block.block_type === 'document' ? (
        <div className="res-document-box">
          {block.document_title && <div className="res-document-title"><strong>{block.document_title}</strong></div>}
          <pre>{block.content}</pre>
          <button type="button" className="doc-copy-btn" onClick={copyDoc}>
            <FileText size={13} aria-hidden="true" /> {copiedDoc ? 'Draft copied' : 'Copy prepared draft'}
          </button>
        </div>
      ) : useList && block.block_type === 'immediate_actions' ? (
        <ol className="res-list res-list-ordered">
          {block.items.map((item, idx) => (
            <li key={idx}>
              <span className="res-list-num">{idx + 1}</span>
              <span className="res-list-text">{item}</span>
            </li>
          ))}
        </ol>
      ) : useList ? (
        <ul className="res-list res-list-bulleted">
          {block.items.map((item, idx) => (
            <li key={idx}>
              <span className="res-list-bullet">•</span>
              <span className="res-list-text">{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="res-block-body">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            skipHtml
            components={citationComponents(sources, onSources)}
          >
            {enhanceListReadability(formatInlineCitations(block.content))}
          </ReactMarkdown>
        </div>
      )}
      {block.block_type === 'human_handoff' && onOpenCase && (
        <button type="button" className="handoff-open-btn" onClick={onOpenCase}>
          <Scale size={14} aria-hidden="true" /> Open Lawyer Escalation Bundle in Your case
        </button>
      )}
    </section>
  )
}

export default function MessageView({
  message,
  onSources,
  onRetry,
  onSpeech,
  onOpenCase,
  thoughtDuration,
}:{
  message:Message
  onSources:(s:Source[], focus?:number)=>void
  onRetry?:()=>void
  onSpeech?:()=>void
  onOpenCase?:()=>void
  thoughtDuration?:number|null
}) {
  const [copied,setCopied]=useState(false)
  const [copiedDoc,setCopiedDoc]=useState(false)
  async function copy(){await navigator.clipboard.writeText(plainCitations(message.content,message.metadata?.sources));setCopied(true);setTimeout(()=>setCopied(false),1200)}
  const needsConfirmation=message.metadata?.events?.some(event=>event.status==='confirmation_required')
  const blocks=message.role==='assistant'?message.metadata?.resolution_blocks:undefined
  const safetyItems=message.role==='assistant'?message.metadata?.safety_messages:undefined
  // The answer text repeats the safety guidance for exports and copying; the banner already shows it.
  const answerText=(safetyItems||[]).reduce((text,item)=>item.text?text.replace(item.text,''):text,message.content).trim()
  const docBlock = blocks?.find(b => b.block_type === 'document')

  async function copyDoc(content: string) {
    await navigator.clipboard.writeText(content)
    setCopiedDoc(true)
    setTimeout(() => setCopiedDoc(false), 1200)
  }

  return <article className={`message ${message.role}`}>
    <div className="avatar" aria-hidden="true">
      {message.role==='assistant'?<Scale size={16} />:'You'}
    </div>
    <div className="message-body">
      <div className="message-header-row">
        <div className="message-role">{message.role==='assistant'?'Nyay Saathi':'You'}</div>
        {message.role==='assistant' && thoughtDuration && (
          <div className="thought-duration-badge" title="Response generation and verification time">
            <Sparkles size={11} aria-hidden="true" />
            <span>Thought for {thoughtDuration}s</span>
          </div>
        )}
      </div>
      {message.role==='assistant' ? (
        <div className="assistant-content">
          {safetyItems?.map(item => (
            <div className="safety-banner" key={item.content_id} role="alert">
              <Siren size={18} aria-hidden="true" color="var(--danger)" />
              <p>{item.text}</p>
            </div>
          ))}
          <div className="prose-content">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              skipHtml
              components={citationComponents(message.metadata?.sources, onSources)}
            >
              {enhanceListReadability(formatInlineCitations(answerText))}
            </ReactMarkdown>
            {docBlock && (
              <div className="res-document-box">
                {docBlock.document_title && <div className="res-document-title"><strong>{docBlock.document_title}</strong></div>}
                <pre>{docBlock.content}</pre>
                <button type="button" className="doc-copy-btn" onClick={() => copyDoc(docBlock.content)}>
                  <FileText size={13} /> {copiedDoc ? 'Draft copied' : 'Copy prepared draft'}
                </button>
              </div>
            )}
            {blocks?.some(b => b.block_type === 'human_handoff') && onOpenCase && (
              <button type="button" className="handoff-open-btn" onClick={onOpenCase}>
                <Scale size={14} aria-hidden="true" /> Open Lawyer Escalation Bundle in Your case
              </button>
            )}
          </div>
        </div>
      ) : (
        <p>{message.content}</p>
      )}
      {message.metadata?.publication_status==='partial'&&<small className="muted" role="note">Some help is ready. Unverified parts have been left out.</small>}
      {!!message.metadata?.attachment_ids?.length&&<small className="muted">{message.metadata.attachment_ids.length} attached document(s) · view in Your case</small>}
      {needsConfirmation&&<div className="confirmation-card" role="note"><b>One detail needs review</b><span>Reply naturally with the correct detail. You do not need to use a special confirmation phrase.</span></div>}
      <div className="message-actions">
        <button onClick={copy}>{copied?<Check size={15}/>:<Copy size={15}/>} {copied?'Copied':'Copy'}</button>
        {message.metadata?.sources?.length?<button onClick={()=>onSources(message.metadata.sources!)}>Sources · {message.metadata.sources.length}</button>:null}
        {onSpeech&&(message.metadata?.verification?.passed||message.metadata?.verification?.publication_safe)&&<button onClick={onSpeech}><Volume2 size={15}/> Listen</button>}
        {message.status==='failed'&&onRetry&&<button onClick={onRetry}><RotateCcw size={15}/> Retry</button>}
      </div>
    </div>
  </article>
}

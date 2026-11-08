import type { LucideIcon } from 'lucide-react'
import {
  BadgeAlert,
  BadgeCheck,
  Briefcase,
  Building2,
  CalendarClock,
  CheckCircle2,
  CheckSquare,
  CircleCheckBig,
  CircleDot,
  CircleHelp,
  ClipboardList,
  Clock,
  Cpu,
  FileDown,
  FileQuestion,
  FileText,
  FlaskConical,
  Gauge,
  GitFork,
  Globe,
  House,
  Info,
  KeyRound,
  Landmark,
  Languages,
  Lightbulb,
  ListChecks,
  ListTree,
  Lock,
  MessageCircleQuestion,
  MessageSquareQuote,
  PackageX,
  PanelRight,
  Paperclip,
  Route,
  Scale,
  Send,
  Shield,
  ShieldCheck,
  ShoppingBag,
  Siren,
  Swords,
  Truck,
  Undo2,
  Wallet,
} from 'lucide-react'
import type { BlockType, GroundingLabel } from './types'

export interface IconMeta {
  icon: LucideIcon
  label: string
  colorVar: string
  bgVar?: string
}

// 1. Grounding Labels (Trustworthiness of statements)
export const GROUNDING_ICONS: Record<GroundingLabel, IconMeta> = {
  verified_legal_source: {
    icon: ShieldCheck,
    label: 'Verified legal source',
    colorVar: 'var(--jade-ink)',
    bgVar: 'var(--jade-tint)',
  },
  reported_by_user: {
    icon: MessageSquareQuote,
    label: 'Reported by you',
    colorVar: 'var(--muted)',
    bgVar: 'var(--bg)',
  },
  practical_precaution: {
    icon: Lightbulb,
    label: 'Practical step',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  requires_confirmation: {
    icon: CircleHelp,
    label: 'Needs confirmation',
    colorVar: 'var(--warning)',
    bgVar: 'var(--warning-tint)',
  },
}

// 2. Answer Block Types (Semantics of response sections)
export const BLOCK_TYPE_ICONS: Record<BlockType, IconMeta> = {
  direct_answer: {
    icon: CircleCheckBig,
    label: 'Direct answer',
    colorVar: 'var(--jade-ink)',
    bgVar: 'var(--jade-tint)',
  },
  recommended_route: {
    icon: Route,
    label: 'Recommended route',
    colorVar: 'var(--jade-ink)',
    bgVar: 'var(--jade-tint)',
  },
  immediate_actions: {
    icon: ListChecks,
    label: 'Do this now',
    colorVar: 'var(--coral-ink)',
    bgVar: 'var(--coral-tint)',
  },
  alternatives: {
    icon: GitFork,
    label: 'Alternatives',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  evidence_checklist: {
    icon: ClipboardList,
    label: 'Evidence checklist',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  document: {
    icon: FileText,
    label: 'Document / draft',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  question: {
    icon: MessageCircleQuestion,
    label: 'Question',
    colorVar: 'var(--warning)',
    bgVar: 'var(--warning-tint)',
  },
  limitation: {
    icon: Info,
    label: 'Limitation',
    colorVar: 'var(--muted)',
    bgVar: 'var(--bg)',
  },
  human_handoff: {
    icon: Scale,
    label: 'Talk to a lawyer',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--jade-tint)',
  },
}

// 3. Topics / Domains
export const TOPIC_ICONS: Record<string, IconMeta> = {
  consumer: {
    icon: ShoppingBag,
    label: 'Consumer dispute',
    colorVar: 'var(--jade-ink)',
    bgVar: 'var(--jade-tint)',
  },
  police: {
    icon: BadgeAlert,
    label: 'Police / criminal matter',
    colorVar: 'var(--coral-ink)',
    bgVar: 'var(--coral-tint)',
  },
  criminal: {
    icon: BadgeAlert,
    label: 'Police / criminal matter',
    colorVar: 'var(--coral-ink)',
    bgVar: 'var(--coral-tint)',
  },
  tenancy: {
    icon: House,
    label: 'Tenancy / rent issue',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  employment: {
    icon: Briefcase,
    label: 'Employment / workplace',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  other: {
    icon: FileQuestion,
    label: 'Legal inquiry',
    colorVar: 'var(--muted)',
    bgVar: 'var(--bg)',
  },
}

export function getTopicMeta(domain?: string): IconMeta {
  if (!domain) return TOPIC_ICONS.other
  const key = domain.toLowerCase()
  if (key in TOPIC_ICONS) return TOPIC_ICONS[key]
  if (key.includes('crimin') || key.includes('police') || key.includes('arrest') || key.includes('fir')) {
    return TOPIC_ICONS.police
  }
  if (key.includes('consum') || key.includes('refund') || key.includes('product') || key.includes('service')) {
    return TOPIC_ICONS.consumer
  }
  if (key.includes('rent') || key.includes('tenant') || key.includes('house')) {
    return TOPIC_ICONS.tenancy
  }
  if (key.includes('employ') || key.includes('salary') || key.includes('job')) {
    return TOPIC_ICONS.employment
  }
  return TOPIC_ICONS.other
}

// 4. Case States
export const CASE_STATE_ICONS: Record<string, IconMeta> = {
  open: {
    icon: CircleDot,
    label: 'Case open',
    colorVar: 'var(--jade-ink)',
    bgVar: 'var(--jade-tint)',
  },
  waiting: {
    icon: Clock,
    label: 'Awaiting action',
    colorVar: 'var(--warning)',
    bgVar: 'var(--warning-tint)',
  },
  resolved: {
    icon: CheckCircle2,
    label: 'Resolved',
    colorVar: 'var(--success)',
    bgVar: 'var(--jade-tint)',
  },
}

// 5. Starters
export const STARTER_ICONS = {
  refund: {
    icon: Wallet,
    title: 'Refund not received',
    hint: 'Paid online, delivery canceled or item never arrived',
  },
  defective: {
    icon: PackageX,
    title: 'Defective product',
    hint: 'Damaged item, seller refusing return or warranty repair',
  },
  not_delivered: {
    icon: Truck,
    title: 'Non-delivery of goods',
    hint: 'Delivery deadline passed without response or refund',
  },
  return_refused: {
    icon: Undo2,
    title: 'Return or refund refused',
    hint: 'Retailer or portal denied replacement under policy',
  },
}

// 6. Roleplay Stakeholders
export const ROLEPLAY_ICONS: Record<string, IconMeta> = {
  police: {
    icon: Shield,
    label: 'Police Officer',
    colorVar: 'var(--coral-ink)',
    bgVar: 'var(--coral-tint)',
  },
  lawyer: {
    icon: Scale,
    label: 'Advocate / Legal Counsel',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  company: {
    icon: Building2,
    label: 'Company Representative',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  landlord: {
    icon: House,
    label: 'Landlord',
    colorVar: 'var(--warning)',
    bgVar: 'var(--warning-tint)',
  },
  employer: {
    icon: Briefcase,
    label: 'Employer',
    colorVar: 'var(--evergreen)',
    bgVar: 'var(--bg)',
  },
  other: {
    icon: Scale,
    label: 'Counterparty',
    colorVar: 'var(--muted)',
    bgVar: 'var(--bg)',
  },
}

export function getRoleplayMeta(role: string): IconMeta {
  const r = role.toLowerCase()
  if (r.includes('police') || r.includes('station') || r.includes('officer')) return ROLEPLAY_ICONS.police
  if (r.includes('lawyer') || r.includes('advocate') || r.includes('judge')) return ROLEPLAY_ICONS.lawyer
  if (r.includes('company') || r.includes('support') || r.includes('agent')) return ROLEPLAY_ICONS.company
  if (r.includes('landlord') || r.includes('owner') || r.includes('tenant')) return ROLEPLAY_ICONS.landlord
  if (r.includes('employer') || r.includes('manager') || r.includes('hr')) return ROLEPLAY_ICONS.employer
  return ROLEPLAY_ICONS.other
}

// 7. General Section Icons
export const SECTION_ICONS = {
  facts: ListTree,
  timeline: CalendarClock,
  evidence: Paperclip,
  actions: CheckSquare,
  submissions: Send,
  lawyer: Scale,
  privacy: Lock,
  official_source: Landmark,
  certified_source: BadgeCheck,
  web_source: Globe,
  download: FileDown,
  swords: Swords,
  languages: Languages,
  case_panel: PanelRight,
  key: KeyRound,
  cpu: Cpu,
  gauge: Gauge,
  eval: FlaskConical,
  siren: Siren,
}

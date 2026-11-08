import { BookOpenText, GitBranch, Settings, Terminal } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { AgentWorkflow, DevspaceSaveResult, KnowledgeBase } from '../types'
import DevSpacePanel from './DevSpacePanel'
import { AgentWorkflowPanel, KnowledgeBasePanel } from './Drawer'

export type SettingsTab = 'knowledge' | 'workflow' | 'devspace'

export interface SettingsPanelProps {
  initialTab?: SettingsTab
  knowledge: KnowledgeBase | null
  workflow: AgentWorkflow | null
  devspaceEnabled: boolean
  onLoadKnowledge: () => Promise<void>
  onLoadWorkflow: () => Promise<void>
  onDevspaceSaved: (result: DevspaceSaveResult) => void
}

export default function SettingsPanel({
  initialTab = 'devspace',
  knowledge,
  workflow,
  devspaceEnabled,
  onLoadKnowledge,
  onLoadWorkflow,
  onDevspaceSaved,
}: SettingsPanelProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>(devspaceEnabled ? initialTab : 'workflow')

  useEffect(() => {
    if (activeTab === 'knowledge' && !knowledge) {
      void onLoadKnowledge()
    } else if (activeTab === 'workflow' && !workflow) {
      void onLoadWorkflow()
    }
  }, [activeTab, knowledge, workflow, onLoadKnowledge, onLoadWorkflow])

  return (
    <div className="settings-panel">
      {/* Segmented Tab Bar: DevSpace -> Workflow -> Knowledge Base */}
      <div className="settings-tab-bar" role="tablist" aria-label="Settings navigation">
        {devspaceEnabled && (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'devspace'}
            className={`settings-tab-btn ${activeTab === 'devspace' ? 'active' : ''}`}
            onClick={() => setActiveTab('devspace')}
          >
            <Terminal size={15} />
            <span>DevSpace</span>
          </button>
        )}
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'workflow'}
          className={`settings-tab-btn ${activeTab === 'workflow' ? 'active' : ''}`}
          onClick={() => setActiveTab('workflow')}
        >
          <GitBranch size={15} />
          <span>Agent Workflow</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'knowledge'}
          className={`settings-tab-btn ${activeTab === 'knowledge' ? 'active' : ''}`}
          onClick={() => setActiveTab('knowledge')}
        >
          <BookOpenText size={15} />
          <span>Knowledge Base</span>
        </button>
      </div>

      {/* Tab Contents */}
      <div className="settings-tab-body">
        {activeTab === 'devspace' && devspaceEnabled && (
          <DevSpacePanel onSaved={onDevspaceSaved} />
        )}

        {activeTab === 'workflow' && (
          workflow ? (
            <AgentWorkflowPanel data={workflow} />
          ) : (
            <div className="panel-content">
              <p>Loading workflow definition…</p>
            </div>
          )
        )}

        {activeTab === 'knowledge' && (
          knowledge ? (
            <KnowledgeBasePanel data={knowledge} />
          ) : (
            <div className="panel-content">
              <p>Loading indexed legal sources…</p>
            </div>
          )
        )}
      </div>
    </div>
  )
}

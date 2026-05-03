import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import type { DashboardSnapshot } from '../api/client.ts';
import { ERPApiClient } from '../api/client.ts';
import { dashboardSections, quickActions, rowSummary } from './viewModel.ts';

type DashboardScreenProps = {
  client?: ERPApiClient;
};

export function DashboardScreen({ client }: DashboardScreenProps) {
  const api = useMemo(() => client || new ERPApiClient(), [client]);
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string>('');
  const [notice, setNotice] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [actionKey, setActionKey] = useState<string>('');
  const [confirmReset, setConfirmReset] = useState(false);
  const [question, setQuestion] = useState('What needs attention today?');
  const [answer, setAnswer] = useState('');
  const [command, setCommand] = useState('receive PO-1001');
  const [commandMessage, setCommandMessage] = useState('');
  const [workflowBusy, setWorkflowBusy] = useState<'ask' | 'preview' | 'run' | ''>('');

  async function loadDashboard() {
    setLoading(true);
    setError('');
    try {
      setSnapshot(await api.dashboard());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to load dashboard.');
    } finally {
      setLoading(false);
    }
  }

  async function runQuickAction(key: string, payload: Record<string, string | number>) {
    if (payload.action === 'reset' && !confirmReset) {
      setConfirmReset(true);
      setNotice('Tap Confirm Reset Demo Data to reset the sample ERP state.');
      return;
    }
    if (payload.action !== 'reset') {
      setConfirmReset(false);
    }
    setActionKey(key);
    setError('');
    setNotice('');
    try {
      const result = await api.action(payload);
      setSnapshot(result.dashboard);
      setNotice(result.message);
      setConfirmReset(false);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to run action.');
    } finally {
      setActionKey('');
    }
  }

  async function askQuestion() {
    setWorkflowBusy('ask');
    setError('');
    setAnswer('');
    try {
      const result = await api.ask(question);
      setAnswer(result.answer);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to ask ERP.');
    } finally {
      setWorkflowBusy('');
    }
  }

  async function previewCommand() {
    setWorkflowBusy('preview');
    setError('');
    setCommandMessage('');
    try {
      const result = await api.previewCommand(command);
      setCommandMessage(result.message);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to preview command.');
    } finally {
      setWorkflowBusy('');
    }
  }

  async function runCommand() {
    setWorkflowBusy('run');
    setError('');
    setCommandMessage('');
    try {
      const result = await api.runCommand(command);
      setCommandMessage(result.message);
      setSnapshot(await api.dashboard());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to run command.');
    } finally {
      setWorkflowBusy('');
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, [api]);

  if (loading && snapshot === null) {
    return (
      <View style={styles.centerState}>
        <ActivityIndicator accessibilityLabel="Loading ERP dashboard" />
        <Text style={styles.stateText}>Loading ERP dashboard</Text>
      </View>
    );
  }

  if (error && snapshot === null) {
    return (
      <View style={styles.centerState}>
        <Text style={styles.errorText}>{error}</Text>
        <Pressable accessibilityRole="button" onPress={() => void loadDashboard()} style={styles.button}>
          <Text style={styles.buttonText}>Retry</Text>
        </Pressable>
      </View>
    );
  }

  const data = snapshot;
  if (data === null) {
    return null;
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>Agentic ERP</Text>
          <Text style={styles.title}>Operating Snapshot</Text>
        </View>
        <Pressable accessibilityRole="button" onPress={() => void loadDashboard()} style={styles.iconButton}>
          <Text style={styles.iconButtonText}>{loading ? '...' : 'Refresh'}</Text>
        </Pressable>
      </View>

      {error ? <Text style={styles.inlineError}>{error}</Text> : null}
      {notice ? <Text style={styles.notice}>{notice}</Text> : null}

      <View style={styles.kpiGrid}>
        {data.kpis.map((kpi) => (
          <View key={kpi.label} style={styles.kpiCard}>
            <Text style={styles.kpiLabel}>{kpi.label}</Text>
            <Text style={styles.kpiValue}>{kpi.value}</Text>
            <Text style={styles.kpiTrend}>{kpi.trend}</Text>
          </View>
        ))}
      </View>

      <Section title="Risk Flags">
        {data.risk_flags.length === 0 ? (
          <EmptyText>No active risk flags.</EmptyText>
        ) : (
          data.risk_flags.map((risk) => (
            <View key={`${risk.level}-${risk.title}`} style={styles.listItem}>
              <Text style={styles.badge}>{risk.level}</Text>
              <View style={styles.listText}>
                <Text style={styles.itemTitle}>{risk.title}</Text>
                <Text style={styles.itemDetail}>{risk.detail}</Text>
              </View>
            </View>
          ))
        )}
      </Section>

      <Section title="Role Summaries">
        {data.roles.map((role) => (
          <View key={role.role} style={styles.listItem}>
            <Text style={styles.itemTitle}>{role.role}</Text>
            <Text style={styles.itemDetail}>{role.summary}</Text>
          </View>
        ))}
      </Section>

      <Section title="Activity">
        {data.audit_log.length === 0 ? (
          <EmptyText>No workflow activity yet.</EmptyText>
        ) : (
          data.audit_log.map((entry) => (
            <View key={`${entry.timestamp}-${entry.message}`} style={styles.listItem}>
              <Text style={styles.itemTitle}>{entry.message}</Text>
              <Text style={styles.itemDetail}>{entry.timestamp}</Text>
            </View>
          ))
        )}
      </Section>

      <Section title="Ask ERP">
        <TextInput
          accessibilityLabel="Ask ERP question"
          editable={workflowBusy === ''}
          multiline
          onChangeText={setQuestion}
          placeholder="Ask what needs attention today"
          style={styles.input}
          value={question}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: workflowBusy !== '' }}
          disabled={workflowBusy !== ''}
          onPress={() => void askQuestion()}
          style={styles.actionButton}
        >
          <Text style={styles.actionButtonText}>{workflowBusy === 'ask' ? 'Asking...' : 'Ask'}</Text>
        </Pressable>
        {answer ? <Text style={styles.answerText}>{answer}</Text> : null}
      </Section>

      <Section title="Command ERP">
        <TextInput
          accessibilityLabel="ERP command"
          editable={workflowBusy === ''}
          multiline
          onChangeText={setCommand}
          placeholder="Try: receive PO-1001"
          style={styles.input}
          value={command}
        />
        <View style={styles.buttonRow}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: workflowBusy !== '' }}
            disabled={workflowBusy !== ''}
            onPress={() => void previewCommand()}
            style={styles.secondaryButton}
          >
            <Text style={styles.secondaryButtonText}>{workflowBusy === 'preview' ? 'Previewing...' : 'Preview'}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: workflowBusy !== '' }}
            disabled={workflowBusy !== ''}
            onPress={() => void runCommand()}
            style={styles.actionButton}
          >
            <Text style={styles.actionButtonText}>{workflowBusy === 'run' ? 'Running...' : 'Run'}</Text>
          </Pressable>
        </View>
        {commandMessage ? <Text style={styles.answerText}>{commandMessage}</Text> : null}
      </Section>

      <Section title="Quick Actions">
        {quickActions(data).map((action) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={action.key === 'reset' && confirmReset ? 'Confirm reset demo data' : action.label}
            accessibilityState={{ disabled: Boolean(actionKey) }}
            disabled={Boolean(actionKey)}
            key={action.key}
            onPress={() => void runQuickAction(action.key, action.payload)}
            style={[
              styles.actionButton,
              action.tone === 'danger' ? styles.dangerButton : null,
              actionKey ? styles.disabledButton : null,
            ]}
          >
            <Text style={[styles.actionButtonText, action.tone === 'danger' ? styles.dangerButtonText : null]}>
              {actionKey === action.key
                ? 'Working...'
                : action.key === 'reset' && confirmReset
                  ? 'Confirm Reset Demo Data'
                  : action.label}
            </Text>
          </Pressable>
        ))}
      </Section>

      {dashboardSections(data).map((section) => (
        <Section key={section.title} title={section.title}>
          {section.rows.map((row, index) => (
            <Text key={`${section.title}-${index}`} style={styles.tableRow}>
              {rowSummary(row)}
            </Text>
          ))}
        </Section>
      ))}
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function EmptyText({ children }: { children: React.ReactNode }) {
  return <Text style={styles.emptyText}>{children}</Text>;
}

const styles = StyleSheet.create({
  centerState: {
    alignItems: 'center',
    backgroundColor: '#f5f7fb',
    flex: 1,
    gap: 12,
    justifyContent: 'center',
    padding: 24,
  },
  stateText: {
    color: '#374151',
    fontSize: 15,
  },
  errorText: {
    color: '#991b1b',
    fontSize: 15,
    textAlign: 'center',
  },
  button: {
    backgroundColor: '#1f2937',
    borderRadius: 6,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  buttonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  container: {
    backgroundColor: '#f5f7fb',
    gap: 16,
    padding: 20,
  },
  header: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
  },
  eyebrow: {
    color: '#4b5563',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  title: {
    color: '#111827',
    fontSize: 30,
    fontWeight: '800',
    letterSpacing: 0,
  },
  iconButton: {
    backgroundColor: '#ffffff',
    borderColor: '#cbd5e1',
    borderRadius: 6,
    borderWidth: 1,
    minWidth: 82,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  iconButtonText: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
  },
  inlineError: {
    backgroundColor: '#fee2e2',
    borderRadius: 6,
    color: '#991b1b',
    padding: 10,
  },
  notice: {
    backgroundColor: '#dcfce7',
    borderRadius: 6,
    color: '#166534',
    padding: 10,
  },
  kpiGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  kpiCard: {
    backgroundColor: '#ffffff',
    borderColor: '#d9e2ef',
    borderRadius: 8,
    borderWidth: 1,
    flexBasis: '48%',
    flexGrow: 1,
    minWidth: 150,
    padding: 14,
  },
  kpiLabel: {
    color: '#475569',
    fontSize: 12,
    fontWeight: '700',
  },
  kpiValue: {
    color: '#111827',
    fontSize: 24,
    fontWeight: '800',
    letterSpacing: 0,
    marginTop: 8,
  },
  kpiTrend: {
    color: '#64748b',
    fontSize: 12,
    marginTop: 4,
  },
  section: {
    backgroundColor: '#ffffff',
    borderColor: '#d9e2ef',
    borderRadius: 8,
    borderWidth: 1,
    gap: 10,
    padding: 14,
  },
  sectionTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: 0,
  },
  listItem: {
    borderTopColor: '#e5e7eb',
    borderTopWidth: 1,
    gap: 6,
    paddingTop: 10,
  },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: '#eef2ff',
    borderRadius: 6,
    color: '#3730a3',
    fontSize: 12,
    fontWeight: '800',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  listText: {
    gap: 3,
  },
  itemTitle: {
    color: '#111827',
    fontSize: 15,
    fontWeight: '700',
  },
  itemDetail: {
    color: '#4b5563',
    fontSize: 14,
    lineHeight: 20,
  },
  emptyText: {
    color: '#64748b',
    fontSize: 14,
  },
  tableRow: {
    borderTopColor: '#e5e7eb',
    borderTopWidth: 1,
    color: '#374151',
    fontSize: 13,
    lineHeight: 19,
    paddingTop: 9,
  },
  actionButton: {
    backgroundColor: '#1f2937',
    borderRadius: 6,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  actionButtonText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '800',
    textAlign: 'center',
  },
  secondaryButton: {
    backgroundColor: '#ffffff',
    borderColor: '#1f2937',
    borderRadius: 6,
    borderWidth: 1,
    flex: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  secondaryButtonText: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '800',
    textAlign: 'center',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
  },
  input: {
    backgroundColor: '#f8fafc',
    borderColor: '#cbd5e1',
    borderRadius: 6,
    borderWidth: 1,
    color: '#111827',
    fontSize: 15,
    minHeight: 76,
    padding: 12,
    textAlignVertical: 'top',
  },
  answerText: {
    backgroundColor: '#f8fafc',
    borderRadius: 6,
    color: '#374151',
    fontSize: 14,
    lineHeight: 20,
    padding: 10,
  },
  dangerButton: {
    backgroundColor: '#ffffff',
    borderColor: '#dc2626',
    borderWidth: 1,
  },
  dangerButtonText: {
    color: '#b91c1c',
  },
  disabledButton: {
    opacity: 0.55,
  },
});

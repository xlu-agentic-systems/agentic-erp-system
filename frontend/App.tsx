import { StatusBar } from 'expo-status-bar';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

export default function App() {
  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.eyebrow}>Agentic ERP</Text>
        <Text style={styles.title}>Operating Snapshot</Text>
        <View style={styles.panel}>
          <Text style={styles.panelTitle}>React Native shell</Text>
          <Text style={styles.copy}>
            The mobile dashboard will connect to the versioned Python API in the next cycle.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#f5f7fb',
  },
  container: {
    padding: 24,
    gap: 16,
  },
  eyebrow: {
    color: '#4b5563',
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  title: {
    color: '#111827',
    fontSize: 32,
    fontWeight: '800',
    letterSpacing: 0,
  },
  panel: {
    backgroundColor: '#ffffff',
    borderColor: '#d9e2ef',
    borderRadius: 8,
    borderWidth: 1,
    padding: 18,
  },
  panelTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '700',
    letterSpacing: 0,
    marginBottom: 8,
  },
  copy: {
    color: '#374151',
    fontSize: 15,
    lineHeight: 22,
  },
});

/**
 * DistractionLogger — Break-time distraction journal.
 * Category picker + free-text note. Brutalist layout.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  Alert,
} from 'react-native';
import { useTheme } from '../contexts/ThemeContext';
import { logDistraction } from '../api/distractions';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const CATEGORIES = [
  'Phone',
  'Social Media',
  'Noise',
  'Hunger',
  'Wandering Mind',
  'Other',
];

const DistractionLogger = ({ sessionId, onLogged }) => {
  const { theme } = useTheme();
  const { colors } = theme;
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!selectedCategory) return;
    setSubmitting(true);
    try {
      await logDistraction({
        session_id: sessionId,
        category: selectedCategory,
        note: note.trim() || null,
      });
      if (onLogged) onLogged();
      setSelectedCategory(null);
      setNote('');
    } catch (err) {
      Alert.alert('Error', 'Could not log distraction. Will try again later.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={[styles.title, { color: colors.text }]}>
        WHAT BROKE YOUR FOCUS?
      </Text>

      <View style={styles.categories}>
        {CATEGORIES.map((cat) => {
          const isSelected = selectedCategory === cat;
          return (
            <TouchableOpacity
              key={cat}
              onPress={() => setSelectedCategory(cat)}
              style={[
                styles.catButton,
                {
                  borderColor: colors.border,
                  backgroundColor: isSelected ? colors.primary : 'transparent',
                },
              ]}
            >
              <Text
                style={[
                  styles.catText,
                  { color: isSelected ? colors.buttonText : colors.text },
                ]}
              >
                {cat.toUpperCase()}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {selectedCategory && (
        <>
          <TextInput
            value={note}
            onChangeText={setNote}
            placeholder="OPTIONAL NOTE..."
            placeholderTextColor={colors.textSecondary + '88'}
            style={[
              styles.noteInput,
              {
                color: colors.text,
                borderColor: colors.border,
                backgroundColor: colors.inputBg,
              },
            ]}
            multiline
            maxLength={200}
          />

          <TouchableOpacity
            onPress={handleSubmit}
            disabled={submitting}
            style={[
              styles.submitBtn,
              {
                backgroundColor: colors.danger,
                opacity: submitting ? 0.5 : 1,
              },
            ]}
          >
            <Text style={[styles.submitText, { color: '#FFFFFF' }]}>
              {submitting ? 'LOGGING...' : 'LOG DISTRACTION'}
            </Text>
          </TouchableOpacity>
        </>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
  },
  title: {
    ...typography.h3,
    marginBottom: spacing.md,
  },
  categories: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  catButton: {
    borderWidth: 3,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  catText: {
    ...typography.caption,
    fontSize: 12,
  },
  noteInput: {
    borderWidth: 3,
    marginTop: spacing.md,
    padding: spacing.md,
    minHeight: 80,
    ...typography.body,
    textAlignVertical: 'top',
  },
  submitBtn: {
    marginTop: spacing.md,
    padding: spacing.md,
    alignItems: 'center',
  },
  submitText: {
    ...typography.button,
  },
});

export default DistractionLogger;

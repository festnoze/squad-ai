/**
 * IntentionInput — "What will you accomplish?" — brutalist text input.
 */

import React from 'react';
import { View, Text, TextInput, StyleSheet } from 'react-native';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const IntentionInput = ({ value, onChangeText }) => {
  const { theme } = useTheme();
  const { colors } = theme;

  return (
    <View style={styles.container}>
      <Text style={[styles.label, { color: colors.textSecondary }]}>
        INTENTION
      </Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder="WHAT WILL YOU ACCOMPLISH?"
        placeholderTextColor={colors.textSecondary + '88'}
        style={[
          styles.input,
          {
            color: colors.text,
            borderColor: colors.border,
            backgroundColor: colors.inputBg,
          },
        ]}
        multiline={false}
        maxLength={120}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
  },
  label: {
    ...typography.label,
    marginBottom: spacing.sm,
  },
  input: {
    borderWidth: 3,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    ...typography.body,
    letterSpacing: 1,
  },
});

export default IntentionInput;

/**
 * RegisterScreen — Create account. Brutalist form.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const RegisterScreen = ({ navigation }) => {
  const { register, error, isLoading, clearError } = useAuth();
  const { theme } = useTheme();
  const { colors } = theme;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [localError, setLocalError] = useState('');

  const handleRegister = async () => {
    setLocalError('');
    if (!email.trim() || !password.trim()) {
      setLocalError('ALL FIELDS REQUIRED.');
      return;
    }
    if (password !== confirmPassword) {
      setLocalError('PASSWORDS DO NOT MATCH.');
      return;
    }
    if (password.length < 6) {
      setLocalError('PASSWORD MUST BE 6+ CHARACTERS.');
      return;
    }
    try {
      await register(email.trim(), password);
    } catch (err) {
      // Error handled by context
    }
  };

  const displayError = localError || error;

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.background }]}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.content}>
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.text }]}>
            JOIN THE
          </Text>
          <Text style={[styles.title, { color: colors.primary }]}>
            FOCUSED
          </Text>
          <View style={[styles.titleBar, { backgroundColor: colors.primary }]} />
        </View>

        {displayError && (
          <View style={[styles.errorBox, { borderColor: colors.danger }]}>
            <Text style={[styles.errorText, { color: colors.danger }]}>
              {displayError}
            </Text>
          </View>
        )}

        <Text style={[styles.label, { color: colors.textSecondary }]}>
          EMAIL
        </Text>
        <TextInput
          value={email}
          onChangeText={(text) => {
            setEmail(text);
            setLocalError('');
            if (error) clearError();
          }}
          placeholder="YOUR@EMAIL.COM"
          placeholderTextColor={colors.textSecondary + '66'}
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          style={[
            styles.input,
            {
              color: colors.text,
              borderColor: colors.border,
              backgroundColor: colors.inputBg,
            },
          ]}
        />

        <Text style={[styles.label, { color: colors.textSecondary }]}>
          PASSWORD
        </Text>
        <TextInput
          value={password}
          onChangeText={(text) => {
            setPassword(text);
            setLocalError('');
          }}
          placeholder="\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588"
          placeholderTextColor={colors.textSecondary + '66'}
          secureTextEntry
          style={[
            styles.input,
            {
              color: colors.text,
              borderColor: colors.border,
              backgroundColor: colors.inputBg,
            },
          ]}
        />

        <Text style={[styles.label, { color: colors.textSecondary }]}>
          CONFIRM PASSWORD
        </Text>
        <TextInput
          value={confirmPassword}
          onChangeText={(text) => {
            setConfirmPassword(text);
            setLocalError('');
          }}
          placeholder="\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588"
          placeholderTextColor={colors.textSecondary + '66'}
          secureTextEntry
          style={[
            styles.input,
            {
              color: colors.text,
              borderColor: colors.border,
              backgroundColor: colors.inputBg,
            },
          ]}
        />

        <TouchableOpacity
          onPress={handleRegister}
          disabled={isLoading}
          style={[
            styles.button,
            {
              backgroundColor: colors.buttonBg,
              opacity: isLoading ? 0.6 : 1,
            },
          ]}
        >
          {isLoading ? (
            <ActivityIndicator color={colors.buttonText} />
          ) : (
            <Text style={[styles.buttonText, { color: colors.buttonText }]}>
              BEGIN YOUR JOURNEY
            </Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.linkButton}
        >
          <Text style={[styles.linkText, { color: colors.textSecondary }]}>
            ALREADY FOCUSED?{' '}
            <Text style={{ color: colors.primary, fontWeight: '900' }}>
              LOG IN
            </Text>
          </Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.screenPadding,
  },
  header: {
    marginBottom: spacing.lg,
  },
  title: {
    ...typography.h1,
    fontSize: 40,
    lineHeight: 44,
  },
  titleBar: {
    height: 5,
    width: 80,
    marginTop: spacing.sm,
  },
  label: {
    ...typography.label,
    marginBottom: spacing.xs,
    marginTop: spacing.md,
  },
  input: {
    borderWidth: 3,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    ...typography.body,
    letterSpacing: 1,
  },
  button: {
    marginTop: spacing.xl,
    padding: spacing.lg,
    alignItems: 'center',
  },
  buttonText: {
    ...typography.button,
  },
  linkButton: {
    marginTop: spacing.lg,
    alignItems: 'center',
  },
  linkText: {
    ...typography.caption,
  },
  errorBox: {
    borderWidth: 3,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  errorText: {
    ...typography.caption,
    fontSize: 13,
  },
});

export default RegisterScreen;

/**
 * LoginScreen — Brutalist login. Stark. No fluff.
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

const LoginScreen = ({ navigation }) => {
  const { login, error, isLoading, clearError } = useAuth();
  const { theme } = useTheme();
  const { colors } = theme;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) return;
    try {
      await login(email.trim(), password);
    } catch (err) {
      // Error handled by context
    }
  };

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.background }]}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.content}>
        {/* App title */}
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.primary }]}>
            DEEP
          </Text>
          <Text style={[styles.title, { color: colors.text }]}>
            FOCUS
          </Text>
          <View style={[styles.titleBar, { backgroundColor: colors.primary }]} />
        </View>

        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
          FOCUS IS A MUSCLE. TRAIN IT.
        </Text>

        {/* Error */}
        {error && (
          <View style={[styles.errorBox, { borderColor: colors.danger }]}>
            <Text style={[styles.errorText, { color: colors.danger }]}>
              {error}
            </Text>
          </View>
        )}

        {/* Email */}
        <Text style={[styles.label, { color: colors.textSecondary }]}>
          EMAIL
        </Text>
        <TextInput
          value={email}
          onChangeText={(text) => {
            setEmail(text);
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

        {/* Password */}
        <Text style={[styles.label, { color: colors.textSecondary }]}>
          PASSWORD
        </Text>
        <TextInput
          value={password}
          onChangeText={(text) => {
            setPassword(text);
            if (error) clearError();
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

        {/* Login button */}
        <TouchableOpacity
          onPress={handleLogin}
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
              ENTER THE VOID
            </Text>
          )}
        </TouchableOpacity>

        {/* Register link */}
        <TouchableOpacity
          onPress={() => navigation.navigate('Register')}
          style={styles.linkButton}
        >
          <Text style={[styles.linkText, { color: colors.textSecondary }]}>
            NO ACCOUNT?{' '}
            <Text style={{ color: colors.primary, fontWeight: '900' }}>
              CREATE ONE
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
    marginBottom: spacing.sm,
  },
  title: {
    ...typography.h1,
    fontSize: 48,
    lineHeight: 52,
  },
  titleBar: {
    height: 5,
    width: 80,
    marginTop: spacing.sm,
  },
  subtitle: {
    ...typography.caption,
    marginBottom: spacing.xxl,
    marginTop: spacing.md,
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

export default LoginScreen;

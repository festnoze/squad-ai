/**
 * TagSelector — Horizontal scrollable tag chips. Brutalist: hard borders, no pills.
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  TextInput,
  StyleSheet,
} from 'react-native';
import { useTheme } from '../contexts/ThemeContext';
import { getTags, createTag } from '../api/tags';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const DEFAULT_TAGS = ['Work', 'Study', 'Creative', 'Health', 'Side Project'];

const TagSelector = ({ selectedTag, onSelectTag, customTags = [] }) => {
  const { theme } = useTheme();
  const { colors } = theme;
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [customTagName, setCustomTagName] = useState('');
  const [apiTags, setApiTags] = useState([]);

  // Fetch user's custom tags from API on mount
  useEffect(() => {
    const fetchTags = async () => {
      try {
        const tags = await getTags();
        if (Array.isArray(tags)) {
          setApiTags(tags);
        }
      } catch (err) {
        // Silently fail — use defaults only
      }
    };
    fetchTags();
  }, []);

  // Merge default tags, API tags, and prop-based custom tags, deduplicating by name
  const mergedTagNames = [...DEFAULT_TAGS];
  const seen = new Set(DEFAULT_TAGS.map((t) => t.toLowerCase()));

  [...apiTags, ...customTags].forEach((t) => {
    const name = t.name || t;
    if (!seen.has(name.toLowerCase())) {
      seen.add(name.toLowerCase());
      mergedTagNames.push(name);
    }
  });

  const allTags = mergedTagNames;

  const generateRandomColor = () => {
    const hex = Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0');
    return `#${hex}`;
  };

  const handleAddCustom = async () => {
    const name = customTagName.trim();
    if (!name) return;

    onSelectTag(name);
    setCustomTagName('');
    setShowCustomInput(false);

    try {
      await createTag(name, generateRandomColor());
      const tags = await getTags();
      if (Array.isArray(tags)) {
        setApiTags(tags);
      }
    } catch (_err) {
      // Persist failed (e.g. offline) — tag is still selected locally
    }
  };

  return (
    <View style={styles.container}>
      <Text style={[styles.label, { color: colors.textSecondary }]}>
        FOCUS TAG
      </Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
      >
        {allTags.map((tag) => {
          const isSelected = selectedTag === tag;
          return (
            <TouchableOpacity
              key={tag}
              onPress={() => onSelectTag(tag)}
              style={[
                styles.tag,
                {
                  borderColor: colors.border,
                  backgroundColor: isSelected ? colors.primary : 'transparent',
                },
              ]}
            >
              <Text
                style={[
                  styles.tagText,
                  {
                    color: isSelected ? colors.buttonText : colors.text,
                  },
                ]}
              >
                {tag.toUpperCase()}
              </Text>
            </TouchableOpacity>
          );
        })}
        <TouchableOpacity
          onPress={() => setShowCustomInput(true)}
          style={[styles.tag, styles.addTag, { borderColor: colors.border }]}
        >
          <Text style={[styles.tagText, { color: colors.textSecondary }]}>
            + ADD
          </Text>
        </TouchableOpacity>
      </ScrollView>
      {showCustomInput && (
        <View style={styles.customInputRow}>
          <TextInput
            value={customTagName}
            onChangeText={setCustomTagName}
            placeholder="TAG NAME"
            placeholderTextColor={colors.textSecondary}
            style={[
              styles.customInput,
              {
                color: colors.text,
                borderColor: colors.border,
                backgroundColor: colors.inputBg,
              },
            ]}
            autoFocus
            onSubmitEditing={handleAddCustom}
          />
          <TouchableOpacity
            onPress={handleAddCustom}
            style={[styles.confirmBtn, { backgroundColor: colors.primary }]}
          >
            <Text style={[styles.confirmText, { color: colors.buttonText }]}>
              OK
            </Text>
          </TouchableOpacity>
        </View>
      )}
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
  scrollView: {
    flexGrow: 0,
  },
  scrollContent: {
    gap: spacing.sm,
    paddingRight: spacing.md,
  },
  tag: {
    borderWidth: 3,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  addTag: {
    borderStyle: 'dashed',
  },
  tagText: {
    ...typography.caption,
    fontSize: 13,
  },
  customInputRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  customInput: {
    flex: 1,
    borderWidth: 3,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    ...typography.caption,
  },
  confirmBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    justifyContent: 'center',
  },
  confirmText: {
    ...typography.button,
    fontSize: 14,
  },
});

export default TagSelector;

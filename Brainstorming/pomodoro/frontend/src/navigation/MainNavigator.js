/**
 * MainNavigator — Bottom tab navigation for authenticated users.
 * Brutalist tab bar: no rounded corners, heavy borders.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import TimerScreen from '../screens/TimerScreen';
import BreakScreen from '../screens/BreakScreen';
import ProfileScreen from '../screens/ProfileScreen';
import AnalyticsScreen from '../screens/AnalyticsScreen';
import SettingsScreen from '../screens/SettingsScreen';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';

const Tab = createBottomTabNavigator();
const TimerStack = createNativeStackNavigator();

// Timer stack includes Timer + Break screens
const TimerStackNavigator = () => {
  return (
    <TimerStack.Navigator screenOptions={{ headerShown: false }}>
      <TimerStack.Screen name="Timer" component={TimerScreen} />
      <TimerStack.Screen name="Break" component={BreakScreen} />
    </TimerStack.Navigator>
  );
};

// Brutalist tab icon — just text, no icons
const TabLabel = ({ label, focused, color }) => (
  <View style={styles.tabLabelContainer}>
    <Text
      style={[
        styles.tabLabel,
        {
          color,
          fontWeight: focused ? '900' : '500',
        },
      ]}
    >
      {label}
    </Text>
    {focused && (
      <View style={[styles.tabIndicator, { backgroundColor: color }]} />
    )}
  </View>
);

const MainNavigator = () => {
  const { theme } = useTheme();
  const { colors } = theme;

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.tabBar,
          borderTopColor: colors.tabBarBorder,
          borderTopWidth: 3,
          height: 70,
          paddingBottom: 8,
          paddingTop: 8,
          borderRadius: 0,
          elevation: 0,
          shadowOpacity: 0,
        },
        tabBarActiveTintColor: colors.tabActive,
        tabBarInactiveTintColor: colors.tabInactive,
        tabBarShowLabel: true,
        tabBarLabelStyle: {
          ...typography.label,
          fontSize: 10,
        },
      }}
    >
      <Tab.Screen
        name="TimerTab"
        component={TimerStackNavigator}
        options={{
          tabBarLabel: ({ focused, color }) => (
            <TabLabel label="FOCUS" focused={focused} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Analytics"
        component={AnalyticsScreen}
        options={{
          tabBarLabel: ({ focused, color }) => (
            <TabLabel label="STATS" focused={focused} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          tabBarLabel: ({ focused, color }) => (
            <TabLabel label="PROFILE" focused={focused} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{
          tabBarLabel: ({ focused, color }) => (
            <TabLabel label="CONFIG" focused={focused} color={color} />
          ),
        }}
      />
    </Tab.Navigator>
  );
};

const styles = StyleSheet.create({
  tabLabelContainer: {
    alignItems: 'center',
    gap: 2,
  },
  tabLabel: {
    ...typography.label,
    fontSize: 10,
  },
  tabIndicator: {
    width: 20,
    height: 3,
  },
});

export default MainNavigator;

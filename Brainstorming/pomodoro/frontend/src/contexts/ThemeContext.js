/**
 * ThemeContext — Realm-based theming. The entire UI transforms
 * when you switch realms.
 */

import React, { createContext, useContext, useState, useEffect } from 'react';
import { getRealmById } from '../theme/realms';
import { storeRealm, getRealm } from '../utils/storage';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const ThemeContext = createContext(null);

export const ThemeProvider = ({ children }) => {
  const [activeRealmId, setActiveRealmId] = useState('void');
  const [realm, setRealm] = useState(getRealmById('void'));

  useEffect(() => {
    const loadRealm = async () => {
      const savedRealm = await getRealm();
      if (savedRealm) {
        setActiveRealmId(savedRealm);
        setRealm(getRealmById(savedRealm));
      }
    };
    loadRealm();
  }, []);

  const switchRealm = async (realmId) => {
    const newRealm = getRealmById(realmId);
    setActiveRealmId(realmId);
    setRealm(newRealm);
    await storeRealm(realmId);
  };

  const theme = {
    colors: realm.colors,
    typography,
    spacing,
    realm,
    activeRealmId,
  };

  return (
    <ThemeContext.Provider value={{ theme, switchRealm, activeRealmId }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export default ThemeContext;

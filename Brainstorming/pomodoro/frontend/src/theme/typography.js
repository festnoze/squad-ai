/**
 * Typography — Brutalist, bold, monospace timer, sans-serif body.
 * Every font weight is intentional. Nothing soft.
 */

import { Platform } from 'react-native';

const MONO = Platform.OS === 'ios' ? 'Courier' : 'monospace';
const SANS = Platform.OS === 'ios' ? 'Helvetica Neue' : 'sans-serif';

const typography = {
  timer: {
    fontFamily: MONO,
    fontSize: 96,
    fontWeight: '900',
    letterSpacing: 8,
  },
  timerSmall: {
    fontFamily: MONO,
    fontSize: 48,
    fontWeight: '900',
    letterSpacing: 4,
  },
  h1: {
    fontFamily: SANS,
    fontSize: 32,
    fontWeight: '900',
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  h2: {
    fontFamily: SANS,
    fontSize: 24,
    fontWeight: '800',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  h3: {
    fontFamily: SANS,
    fontSize: 18,
    fontWeight: '700',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  body: {
    fontFamily: SANS,
    fontSize: 16,
    fontWeight: '400',
    letterSpacing: 0.5,
  },
  bodyBold: {
    fontFamily: SANS,
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  caption: {
    fontFamily: SANS,
    fontSize: 12,
    fontWeight: '500',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  button: {
    fontFamily: SANS,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  mono: {
    fontFamily: MONO,
    fontSize: 14,
    fontWeight: '400',
  },
  stat: {
    fontFamily: MONO,
    fontSize: 36,
    fontWeight: '900',
    letterSpacing: 2,
  },
  label: {
    fontFamily: SANS,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
};

export default typography;

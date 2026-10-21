/**
 * AnimatedSplash — tela de splash animada exibida durante o boot do app.
 *
 * Mostra a marca unificada do GasFlow com animações de fade + scale + pulse.
 * Chamado por App.tsx enquanto booted === false.
 * Ao montar, dispara as animações; quando o boot termina, faz fade-out.
 */

import React, { useEffect, useRef } from "react";
import {
  View,
  Text,
  Animated,
  StyleSheet,
  StatusBar,
  Dimensions,
} from "react-native";

import Logo from "../components/ui/Logo";
import { colors, spacing, typography } from "../theme";

const { width } = Dimensions.get("window");

interface AnimatedSplashProps {
  visible: boolean;
}

export default function AnimatedSplash({ visible }: AnimatedSplashProps) {
  const logoScale = useRef(new Animated.Value(0.3)).current;
  const logoOpacity = useRef(new Animated.Value(0)).current;
  const textOpacity = useRef(new Animated.Value(0)).current;
  const subtitleOpacity = useRef(new Animated.Value(0)).current;
  const pulseScale = useRef(new Animated.Value(1)).current;
  const containerOpacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!visible) {
      // Fade-out quando o boot termina
      Animated.timing(containerOpacity, {
        toValue: 0,
        duration: 400,
        useNativeDriver: true,
      }).start();
      return;
    }

    // Sequência de entrada
    Animated.sequence([
      // Logo aparece com scale
      Animated.parallel([
        Animated.spring(logoScale, {
          toValue: 1,
          friction: 6,
          tension: 40,
          useNativeDriver: true,
        }),
        Animated.timing(logoOpacity, {
          toValue: 1,
          duration: 500,
          useNativeDriver: true,
        }),
      ]),
      // Texto aparece
      Animated.timing(textOpacity, {
        toValue: 1,
        duration: 400,
        useNativeDriver: true,
      }),
      // Subtítulo aparece
      Animated.timing(subtitleOpacity, {
        toValue: 1,
        duration: 400,
        useNativeDriver: true,
      }),
    ]).start();

    // Pulse contínuo no logo
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseScale, {
          toValue: 1.08,
          duration: 1200,
          useNativeDriver: true,
        }),
        Animated.timing(pulseScale, {
          toValue: 1,
          duration: 1200,
          useNativeDriver: true,
        }),
      ])
    );
    pulse.start();

    return () => pulse.stop();
  }, [visible, logoScale, logoOpacity, textOpacity, subtitleOpacity, pulseScale, containerOpacity]);

  if (!visible) return null;

  return (
    <Animated.View style={[styles.container, { opacity: containerOpacity }]} testID="animated-splash">
      <StatusBar barStyle="light-content" backgroundColor={colors.background} />

      {/* Glow de fundo */}
      <View style={styles.glow} />

      {/* Logo com pulse */}
      <Animated.View
        style={[
          styles.logoContainer,
          {
            opacity: logoOpacity,
            transform: [{ scale: Animated.multiply(logoScale, pulseScale) }],
          },
        ]}
      >
        <Logo size={104} />
      </Animated.View>

      {/* Título */}
      <Animated.Text style={[styles.title, { opacity: textOpacity }]}>
        GasFlow
      </Animated.Text>

      {/* Subtítulo */}
      <Animated.Text style={[styles.subtitle, { opacity: subtitleOpacity }]}>
        Sistema Operacional de Entregas
      </Animated.Text>

      {/* Barra de progresso animada */}
      <View style={styles.progressContainer}>
        <View style={styles.progressTrack}>
          <Animated.View
            style={[
              styles.progressFill,
              {
                opacity: subtitleOpacity,
              },
            ]}
          />
        </View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.background,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9999,
  },
  glow: {
    position: "absolute",
    width: width * 0.7,
    height: width * 0.7,
    borderRadius: (width * 0.7) / 2,
    backgroundColor: colors.brandSoft,
    top: "28%",
  },
  logoContainer: {
    marginBottom: spacing.xl,
  },
  title: {
    fontSize: typography.display,
    fontWeight: "800",
    color: colors.foreground,
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: typography.label,
    color: colors.mutedForeground,
    marginTop: spacing.sm,
    letterSpacing: 0.6,
  },
  progressContainer: {
    position: "absolute",
    bottom: 80,
    width: 120,
  },
  progressTrack: {
    height: 3,
    borderRadius: 2,
    backgroundColor: colors.surfaceMuted,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    width: "60%",
    borderRadius: 2,
    backgroundColor: colors.brand,
  },
});

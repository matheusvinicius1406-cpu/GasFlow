/**
 * AnimatedSplash — tela de splash animada exibida durante o boot do app.
 *
 * Mostra o logo do GasFlow com animações de fade + scale + pulse.
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
      <StatusBar barStyle="dark-content" backgroundColor="#ffffff" />

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
        <View style={styles.logoCircle}>
          <Text style={styles.logoEmoji}>🔥</Text>
        </View>
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
    backgroundColor: "#ffffff",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9999,
  },
  glow: {
    position: "absolute",
    width: width * 0.6,
    height: width * 0.6,
    borderRadius: (width * 0.6) / 2,
    backgroundColor: "rgba(255, 107, 0, 0.08)",
    top: "30%",
  },
  logoContainer: {
    marginBottom: 24,
  },
  logoCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: "#FF6B00",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#FF6B00",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
  },
  logoEmoji: {
    fontSize: 48,
  },
  title: {
    fontSize: 32,
    fontWeight: "800",
    color: "#1a1a1a",
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 14,
    color: "#666",
    marginTop: 8,
    letterSpacing: 0.5,
  },
  progressContainer: {
    position: "absolute",
    bottom: 80,
    width: 120,
  },
  progressTrack: {
    height: 3,
    backgroundColor: "#e5e5e5",
    borderRadius: 2,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    width: "60%",
    backgroundColor: "#FF6B00",
    borderRadius: 2,
  },
});

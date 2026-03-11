import VoiceAgent from "@/components/VoiceAgent";

export default function Home() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--background)",
        padding: "1rem",
      }}
    >
      <VoiceAgent />
    </main>
  );
}

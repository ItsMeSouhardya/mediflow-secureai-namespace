/**
 * Static informational pages — task 14.12
 *
 * Four pages in one file (all are pure content, no API calls):
 *   /privacy               Privacy policy
 *   /ai-limitations        AI decision-support limitations and disclaimers
 *   /emergency-guidance    When and how to call emergency services
 *   /consent-explanation   How consent and data sharing works
 */

import { Link } from 'react-router-dom'
import { Card, PageHeader, Alert } from '../components/ui/index'

// ---------------------------------------------------------------------------
// Shared layout wrapper
// ---------------------------------------------------------------------------
function InfoLayout({ eyebrow, title, subtitle, children }) {
  return (
    <main className="min-h-screen bg-slate-50 px-4 pb-16 pt-24 sm:px-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <PageHeader eyebrow={eyebrow} title={title} subtitle={subtitle} />
        {children}
        <p className="text-xs text-slate-400 text-center pt-4">
          MediFlow Secure · Last updated July 2026
        </p>
      </div>
    </main>
  )
}

function Section({ title, children }) {
  return (
    <Card className="p-6 space-y-3">
      <h2 className="text-base font-extrabold text-slate-900">{title}</h2>
      <div className="text-sm text-slate-600 space-y-2 leading-relaxed">
        {children}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Privacy Policy
// ---------------------------------------------------------------------------
export function PrivacyPage() {
  return (
    <InfoLayout
      eyebrow="Legal"
      title="Privacy Policy"
      subtitle="How MediFlow Secure collects, uses, and protects your personal health information."
    >
      <Alert variant="info" title="Summary">
        Your medical data is encrypted at rest and in transit. We never sell or share your data
        with third parties without your explicit consent. You can export or delete your data at
        any time by contacting support.
      </Alert>

      <Section title="1. What data we collect">
        <p>We collect the minimum information necessary to provide healthcare management services:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>Identity data (name, email or phone) used for authentication</li>
          <li>Health records you enter or that a clinician records during a visit</li>
          <li>Uploaded medical documents (stored encrypted; never shared without consent)</li>
          <li>Queue and appointment activity</li>
          <li>Audit logs of who accessed your records and when</li>
        </ul>
      </Section>

      <Section title="2. How we use your data">
        <ul className="list-disc pl-5 space-y-1">
          <li>To operate the hospital queue, appointment, and telemedicine system</li>
          <li>To provide AI-assisted health summaries (<strong>decision support only — not diagnosis</strong>)</li>
          <li>To allow authorised clinicians to view relevant records with your consent</li>
          <li>To detect and prevent unauthorised access (security monitoring)</li>
        </ul>
        <p>We do not use your data for advertising, profiling, or sale to third parties.</p>
      </Section>

      <Section title="3. Data security">
        <ul className="list-disc pl-5 space-y-1">
          <li>All documents are encrypted with per-file keys (AES-Fernet envelope encryption)</li>
          <li>Access requires authentication, role verification, and explicit patient consent</li>
          <li>Every access to clinical records is logged in an immutable audit trail</li>
          <li>Document integrity is anchored on a blockchain proof layer</li>
        </ul>
      </Section>

      <Section title="4. Your rights">
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Access:</strong> View all your records in the Health Record section</li>
          <li><strong>Consent control:</strong> Grant, limit, or revoke clinician access at any time</li>
          <li><strong>Audit history:</strong> See who accessed your records in the Integrity section</li>
          <li><strong>Deletion:</strong> Contact support to request account and data deletion</li>
        </ul>
      </Section>

      <Section title="5. Contact">
        <p>
          For privacy questions or data requests, contact our Data Protection Officer at{' '}
          <a href="mailto:privacy@mediflow.example" className="text-blue-700 underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">
            privacy@mediflow.example
          </a>.
        </p>
      </Section>
    </InfoLayout>
  )
}

// ---------------------------------------------------------------------------
// AI Limitations
// ---------------------------------------------------------------------------
export function AILimitationsPage() {
  return (
    <InfoLayout
      eyebrow="Clinical Safety"
      title="AI Limitations & Disclaimers"
      subtitle="Understanding the boundaries of AI-assisted features in MediFlow Secure."
    >
      <Alert variant="error" title="AI outputs are decision support only — NOT diagnoses">
        No AI-generated result on this platform constitutes a medical diagnosis, clinical
        recommendation, or substitute for professional medical evaluation. All AI outputs
        require review by a qualified healthcare professional before any clinical action.
      </Alert>

      <Section title="What AI features are present">
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Symptom triage:</strong> Estimates severity and suggests a department. May miss serious conditions — always call emergency services if in doubt.</li>
          <li><strong>Lab report extraction:</strong> Identifies biomarker values from uploaded PDFs using pattern matching. May miss non-standard formats or produce incorrect values.</li>
          <li><strong>Diabetes and cardiovascular risk:</strong> Simplified heuristic models based on a small set of inputs. Not validated on clinical populations.</li>
          <li><strong>Queue wait estimation:</strong> Based on queue position and historical consultation times. Actual wait may differ significantly.</li>
        </ul>
      </Section>

      <Section title="Known limitations">
        <ul className="list-disc pl-5 space-y-1">
          <li>Models have not been validated on the target patient population</li>
          <li>Biomarker extraction may fail on scanned, handwritten, or non-English reports</li>
          <li>Risk models do not account for ethnicity, medication effects, or full medical history</li>
          <li>A low risk score does not rule out disease; a high score does not confirm it</li>
          <li>Emergency symptom escalation uses keyword matching and may miss atypical presentations</li>
        </ul>
      </Section>

      <Section title="Model versions and traceability">
        <p>
          Every AI result is stored with its model version, rule version, and timestamp so
          outputs are reproducible and traceable. Review status is shown alongside every
          result — outputs labelled <em>pending</em> have not yet been accepted by a clinician.
        </p>
      </Section>

      <Section title="What to do if you are concerned">
        <ul className="list-disc pl-5 space-y-1">
          <li>If you have an emergency, call emergency services immediately (112 / 911)</li>
          <li>Discuss any AI result with your doctor before acting on it</li>
          <li>Report incorrect AI outputs via Settings → Feedback</li>
        </ul>
      </Section>
    </InfoLayout>
  )
}

// ---------------------------------------------------------------------------
// Emergency Guidance
// ---------------------------------------------------------------------------
export function EmergencyGuidancePage() {
  return (
    <InfoLayout
      eyebrow="Emergency"
      title="Emergency Guidance"
      subtitle="What to do in a medical emergency — do not rely on this system in a life-threatening situation."
    >
      <Alert variant="error" title="If you or someone nearby is in immediate danger — call 112 or 911 NOW">
        Do not use this application to manage a life-threatening emergency.
        Call emergency services immediately and follow their instructions.
      </Alert>

      <Section title="When to call emergency services immediately">
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Chest pain</strong> — especially with shortness of breath, sweating, or arm/jaw pain</li>
          <li><strong>Difficulty breathing</strong> — unable to speak in full sentences, blue lips</li>
          <li><strong>Stroke signs</strong> — face drooping, arm weakness, speech difficulty (FAST test)</li>
          <li><strong>Loss of consciousness</strong> — unresponsive or not breathing normally</li>
          <li><strong>Severe bleeding</strong> — bleeding that cannot be controlled with pressure</li>
          <li><strong>Severe allergic reaction</strong> — throat swelling, hives with breathing difficulty</li>
          <li><strong>Seizures</strong> — convulsions lasting more than 5 minutes</li>
        </ul>
        <p className="font-bold mt-2">Emergency number: 112 (EU) · 911 (US) · 999 (UK)</p>
      </Section>

      <Section title="FAST stroke test">
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>F</strong>ace — ask the person to smile. Does one side droop?</li>
          <li><strong>A</strong>rms — ask them to raise both arms. Does one drift down?</li>
          <li><strong>S</strong>peech — ask them to repeat a simple phrase. Is it slurred?</li>
          <li><strong>T</strong>ime — if any of the above: call emergency services immediately</li>
        </ul>
      </Section>

      <Section title="Using MediFlow Emergency Triage">
        <p>
          The{' '}
          <Link to="/emergency" className="text-blue-700 underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">
            Emergency Triage
          </Link>
          {' '}feature provides AI-assisted severity estimation only.
          It is <strong>not a replacement for calling emergency services</strong>.
          If the system suggests "Emergency" — call 112/911 immediately; do not drive yourself.
        </p>
      </Section>

      <Section title="Suicide and crisis support">
        <p>
          If you are experiencing thoughts of self-harm, contact emergency services (112/911)
          or a crisis helpline. In many countries you can also call or text 988 (Suicide &amp;
          Crisis Lifeline) for immediate support.
        </p>
      </Section>
    </InfoLayout>
  )
}

// ---------------------------------------------------------------------------
// Consent Explanation
// ---------------------------------------------------------------------------
export function ConsentExplanationPage() {
  return (
    <InfoLayout
      eyebrow="Privacy & Control"
      title="How Consent Works"
      subtitle="You are in control of who can access your medical records and for how long."
    >
      <Alert variant="info" title="Your records are yours">
        No doctor or hospital can access your health records without your explicit approval —
        except in a documented emergency (break-glass), which is immediately logged and notified to you.
      </Alert>

      <Section title="Normal access request flow">
        <ol className="list-decimal pl-5 space-y-1">
          <li>A doctor submits an access request with a stated purpose and scope</li>
          <li>You receive a notification in your consent inbox</li>
          <li>You review the request and choose which record categories to share and for how long</li>
          <li>Access is automatically cut off when the period expires — no action needed</li>
          <li>You can revoke access at any time from <Link to="/sharing" className="text-blue-700 underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">Sharing &amp; Consent</Link></li>
        </ol>
      </Section>

      <Section title="Record scopes — what you can share">
        <ul className="list-disc pl-5 space-y-1">
          {[
            ['Summary',          'Demographics, MRN, blood group'],
            ['Encounters',       'Visit notes and consultation history'],
            ['Diagnoses',        'Confirmed clinical diagnoses'],
            ['Prescriptions',    'Active and historical medications'],
            ['Allergies',        'Recorded substance allergies'],
            ['Vaccinations',     'Vaccination history'],
            ['Reports',          'Uploaded medical documents (metadata only in shared views)'],
            ['Risk predictions', 'AI-generated risk scores (clinician-accepted only)'],
            ['Monitoring',       'Vital sign observations and alerts'],
          ].map(([scope, desc]) => (
            <li key={scope}><strong>{scope}:</strong> {desc}</li>
          ))}
        </ul>
      </Section>

      <Section title="Emergency break-glass access">
        <p>
          In a documented medical emergency, a doctor can invoke emergency break-glass access.
          This is <strong>immediately logged</strong> with the reason, the doctor's identity, the
          records accessed, and the timestamp. You receive an instant notification. Access expires
          automatically after 4 hours and cannot be extended.
        </p>
        <p>
          If you believe break-glass was misused, contact your hospital's data protection officer
          or report it via the Integrity &amp; Audit section.
        </p>
      </Section>

      <Section title="Cross-hospital sharing">
        <p>
          If a doctor at a different hospital requests access, you will receive a separate
          cross-hospital share request. The same grant/deny/revoke process applies. Shared
          responses show only the approved record categories — raw document files are never
          sent to external parties.
        </p>
      </Section>

      <Section title="Audit trail">
        <p>
          Every access to your records — successful or denied — is logged immutably and can
          be viewed in{' '}
          <Link to="/integrity" className="text-blue-700 underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">
            Integrity &amp; Audit
          </Link>.
        </p>
      </Section>
    </InfoLayout>
  )
}

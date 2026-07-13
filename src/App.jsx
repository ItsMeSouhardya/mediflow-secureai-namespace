import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Footer from './components/Footer'

// Existing pages
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import QueueTracker from './pages/QueueTracker'
import Bookings from './pages/Bookings'
import Emergency from './pages/Emergency'
import AISmartReport from './pages/AISmartReport'
import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import Unauthorized from './pages/Unauthorized'
import ResetPassword from './pages/ResetPassword'
import ActivateAccount from './pages/ActivateAccount'
import SessionExpired from './pages/SessionExpired'
import PatientEHR from './pages/PatientEHR'
import DoctorEHRWorkspace from './pages/DoctorEHRWorkspace'
import IntegrityVerification from './pages/IntegrityVerification'
import PatientSharing from './pages/PatientSharing'
import IncomingShares from './pages/IncomingShares'
import PatientMonitoring from './pages/PatientMonitoring'
import DoctorMonitoring from './pages/DoctorMonitoring'
import SecurityDashboard from './pages/SecurityDashboard'
import Profile from './pages/Profile'

// Task 16 — Final integrated demonstration
import DemoPage from './pages/DemoPage'

// Task 14 — new integrated dashboards
import DoctorDashboard from './pages/DoctorDashboard'
import HospitalAdminDashboard from './pages/HospitalAdminDashboard'

// Task 14.12 — informational pages
import {
  PrivacyPage,
  AILimitationsPage,
  EmergencyGuidancePage,
  ConsentExplanationPage,
} from './pages/InfoPages'
import ContactUs from './pages/ContactUs'

import { AuthProvider } from './auth/AuthContext'
import ProtectedRoute from './auth/ProtectedRoute'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="bg-surface text-on-surface antialiased min-h-screen flex flex-col">
          <Navbar />
          <main className="flex-1" id="main-content">
            <a
              href="#main-content"
              className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[999] focus:rounded-xl focus:bg-blue-700 focus:px-4 focus:py-2 focus:text-sm focus:font-bold focus:text-white focus:shadow-lg"
            >
              Skip to main content
            </a>

            <Routes>
              {/* ---- Public ---- */}
              <Route path="/" element={<Landing />} />
              <Route path="/demo" element={<DemoPage />} />
              <Route path="/queue" element={<QueueTracker />} />
              <Route path="/emergency" element={<Emergency />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="/activate" element={<ActivateAccount />} />
              <Route path="/unauthorized" element={<Unauthorized />} />
              <Route path="/session-expired" element={<SessionExpired />} />

              {/* ---- Informational (14.12) ---- */}
              <Route path="/privacy" element={<PrivacyPage />} />
              <Route path="/ai-limitations" element={<AILimitationsPage />} />
              <Route path="/emergency-guidance" element={<EmergencyGuidancePage />} />
              <Route path="/consent-explanation" element={<ConsentExplanationPage />} />
              <Route path="/contact" element={<ContactUs />} />

              {/* ---- Patient ---- */}
              <Route path="/patient-dashboard" element={
                <ProtectedRoute roles={['patient']}><Navigate to="/health-record" replace /></ProtectedRoute>
              } />
              <Route path="/bookings" element={
                <ProtectedRoute roles={['patient']}><Bookings /></ProtectedRoute>
              } />
              <Route path="/health-record" element={
                <ProtectedRoute roles={['patient']}><PatientEHR /></ProtectedRoute>
              } />
              <Route path="/monitoring" element={
                <ProtectedRoute roles={['patient']}><PatientMonitoring /></ProtectedRoute>
              } />
              <Route path="/sharing" element={
                <ProtectedRoute roles={['patient']}><PatientSharing /></ProtectedRoute>
              } />
              <Route path="/integrity" element={
                <ProtectedRoute roles={['patient']}><IntegrityVerification /></ProtectedRoute>
              } />
              <Route path="/ai-report" element={
                <ProtectedRoute roles={['patient', 'doctor']}><AISmartReport /></ProtectedRoute>
              } />
              <Route path="/profile" element={
                <ProtectedRoute><Profile /></ProtectedRoute>
              } />

              {/* ---- Doctor ---- */}
              <Route path="/doctor-dashboard" element={
                <ProtectedRoute roles={['doctor']}><DoctorDashboard /></ProtectedRoute>
              } />
              <Route path="/clinical-workspace" element={
                <ProtectedRoute roles={['doctor']}><DoctorEHRWorkspace /></ProtectedRoute>
              } />
              <Route path="/monitoring/triage" element={
                <ProtectedRoute roles={['doctor']}><DoctorMonitoring /></ProtectedRoute>
              } />
              <Route path="/incoming-shares" element={
                <ProtectedRoute roles={['doctor', 'hospital_admin']}><IncomingShares /></ProtectedRoute>
              } />

              {/* ---- Hospital Admin ---- */}
              <Route path="/admin-dashboard" element={
                <ProtectedRoute roles={['hospital_admin']}><HospitalAdminDashboard /></ProtectedRoute>
              } />

              {/* ---- Security Admin ---- */}
              <Route path="/security" element={
                <ProtectedRoute roles={['security_admin']}><SecurityDashboard /></ProtectedRoute>
              } />

              {/* ---- Public hospital dashboard ---- */}
              <Route path="/dashboard" element={<Dashboard />} />
            </Routes>
          </main>
          <Footer />
        </div>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App

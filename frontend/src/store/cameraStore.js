import { create } from 'zustand'
import api from '../services/api'
import { subscribeCamera, unsubscribeCamera } from '../services/socket'

const useCameraStore = create((set, get) => ({
    cameras: [],
    loading: false,
    error: null,
    frames: {},  // camera_id -> blob URL

    fetchCameras: async () => {
        set({ loading: true, error: null })
        try {
            const res = await api.get('/api/cameras')
            set({ cameras: res.data, loading: false })
        } catch (err) {
            set({ error: err.message, loading: false })
        }
    },

    addCamera: async (data) => {
        const res = await api.post('/api/cameras', data)
        set((s) => ({ cameras: [...s.cameras, res.data] }))
        return res.data
    },

    deleteCamera: async (cameraId) => {
        await api.delete(`/api/cameras/${cameraId}`)
        set((s) => ({ cameras: s.cameras.filter(c => c.camera_id !== cameraId) }))
    },

    startCamera: async (cameraId) => {
        await api.post(`/api/cameras/${cameraId}/start`)
        // Subscribe to frames IMMEDIATELY — don't wait for state update
        subscribeCamera(cameraId)
        set((s) => ({
            cameras: s.cameras.map(c =>
                c.camera_id === cameraId ? { ...c, status: 'running' } : c
            )
        }))
    },

    stopCamera: async (cameraId) => {
        await api.post(`/api/cameras/${cameraId}/stop`)
        unsubscribeCamera(cameraId)
        set((s) => ({
            cameras: s.cameras.map(c =>
                c.camera_id === cameraId ? { ...c, status: 'stopped' } : c
            )
        }))
    },

    // Called when backend emits camera_status event (e.g., thread error)
    updateCameraStatus: (cameraId, status) => {
        set((s) => ({
            cameras: s.cameras.map(c =>
                c.camera_id === cameraId ? { ...c, status } : c
            )
        }))
    },

    updateFrame: (cameraId, jpegB64) => {
        const bytes = atob(jpegB64)
        const arr = new Uint8Array(bytes.length)
        for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
        const blob = new Blob([arr], { type: 'image/jpeg' })
        const url = URL.createObjectURL(blob)

        // Revoke previous
        const prev = get().frames[cameraId]
        if (prev) URL.revokeObjectURL(prev)

        set((s) => ({
            frames: { ...s.frames, [cameraId]: url }
        }))
    },
}))

export default useCameraStore

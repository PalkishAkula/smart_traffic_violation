import { io } from 'socket.io-client'

const SOCKET_URL = 'http://localhost:8000'
const subscribedCameras = new Set()

const socket = io(SOCKET_URL, {
    autoConnect: false,
    transports: ['websocket', 'polling'],
})

function normalizeCameraId(cameraId) {
    return String(cameraId ?? '').trim()
}

socket.on('connect', () => {
    subscribedCameras.forEach((cameraId) => {
        socket.emit('subscribe_camera', { camera_id: cameraId })
    })
})

export function connectSocket() {
    if (!socket.connected) {
        socket.connect()
    }
}

export function disconnectSocket() {
    if (socket.connected) {
        socket.disconnect()
    }
}

export function subscribeCamera(cameraId) {
    const normalized = normalizeCameraId(cameraId)
    if (!normalized || subscribedCameras.has(normalized)) {
        return
    }
    subscribedCameras.add(normalized)
    socket.emit('subscribe_camera', { camera_id: normalized })
}

export function unsubscribeCamera(cameraId) {
    const normalized = normalizeCameraId(cameraId)
    if (!normalized || !subscribedCameras.has(normalized)) {
        return
    }
    subscribedCameras.delete(normalized)
    socket.emit('unsubscribe_camera', { camera_id: normalized })
}

export default socket

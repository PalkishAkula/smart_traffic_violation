import { io } from 'socket.io-client'

const SOCKET_URL = 'http://localhost:8000'

const socket = io(SOCKET_URL, {
    autoConnect: false,
    transports: ['websocket', 'polling'],
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
    socket.emit('subscribe_camera', { camera_id: cameraId })
}

export function unsubscribeCamera(cameraId) {
    socket.emit('unsubscribe_camera', { camera_id: cameraId })
}

export default socket

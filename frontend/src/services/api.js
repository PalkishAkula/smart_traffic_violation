import axios from 'axios'



const API_BASE = 'http://localhost:8000'



const api = axios.create({

    baseURL: API_BASE,

})



// JWT interceptor

api.interceptors.request.use((config) => {

    const token = localStorage.getItem('access_token')

    if (token) {

        config.headers.Authorization = `Bearer ${token}`

    }

    return config

})



api.interceptors.response.use(

    (response) => response,

    (error) => {

        if (error.response?.status === 401) {

            localStorage.removeItem('access_token')

            localStorage.removeItem('user')

            // Don't redirect if already on login page

            if (!window.location.pathname.includes('/login')) {

                window.location.href = '/login'

            }

        }

        return Promise.reject(error)

    }

)



export default api

export { API_BASE }


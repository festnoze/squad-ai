import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios'
import toast from 'react-hot-toast'

// API Configuration
const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000'

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
api.interceptors.request.use(
  (config) => {
    // Add auth token if available
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  (response: AxiosResponse) => {
    return response
  },
  (error: AxiosError) => {
    // Handle common errors
    if (error.response?.status === 401) {
      // Unauthorized - clear token and redirect to login
      localStorage.removeItem('auth_token')
      toast.error('Session expired. Please log in again.')
    } else if (error.response?.status === 403) {
      toast.error('Access denied')
    } else if (error.response?.status === 404) {
      toast.error('Resource not found')
    } else if (error.response?.status === 500) {
      toast.error('Server error. Please try again later.')
    } else if (error.code === 'NETWORK_ERROR') {
      toast.error('Network error. Please check your connection.')
    } else {
      // Generic error message
      const message = (error.response?.data as any)?.detail || error.message || 'An error occurred'
      toast.error(message)
    }

    return Promise.reject(error)
  }
)

// API response types
export interface ApiResponse<T = any> {
  success: boolean
  message?: string
  data?: T
}

export interface PaginatedResponse<T = any> extends ApiResponse<T[]> {
  total: number
  page: number
  size: number
  pages: number
}


// Health check state
let healthCheckPerformed = false
let healthCheckPassed = false
let healthCheckError: string | null = null

// Perform initial health check
const performInitialHealthCheck_async = async (): Promise<void> => {
  if (healthCheckPerformed) return
  
  healthCheckPerformed = true
  try {
    const response = await axios.get(`${API_BASE_URL}/health`, { timeout: 5000 })
    if (response.status === 200 && response.data.status === 'healthy') {
      healthCheckPassed = true
      healthCheckError = null
    } else {
      healthCheckPassed = false
      healthCheckError = 'API health check failed: unexpected response'
      toast.error('API health check failed: unexpected response')
    }
  } catch (error) {
    healthCheckPassed = false
    healthCheckError = `API is not available: ${error instanceof Error ? error.message : 'Unknown error'}`
    toast.error(healthCheckError)
  }
}

// Run health check immediately
performInitialHealthCheck_async()

// Generic API methods
export class ApiClient {
  static async ensureHealthy_async(): Promise<void> {
    if (!healthCheckPerformed) {
      await performInitialHealthCheck_async()
    }
    
    if (!healthCheckPassed) {
      throw new Error(healthCheckError || 'API health check failed')
    }
  }

  static async get<T>(url: string, params?: any): Promise<T> {
    await this.ensureHealthy_async()
    const response = await api.get(url, { params })
    return response.data
  }

  static async post<T>(url: string, data?: any, config?: any): Promise<T> {
    await this.ensureHealthy_async()
    const response = await api.post(url, data, config)
    return response.data
  }

  static async put<T>(url: string, data?: any): Promise<T> {
    await this.ensureHealthy_async()
    const response = await api.put(url, data)
    return response.data
  }

  static async delete<T>(url: string, config?: any): Promise<T> {
    await this.ensureHealthy_async()
    const response = await api.delete(url, config)
    return response.data
  }

  static async patch<T>(url: string, data?: any): Promise<T> {
    await this.ensureHealthy_async()
    const response = await api.patch(url, data)
    return response.data
  }
}

export default api
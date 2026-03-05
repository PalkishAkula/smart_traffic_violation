import { create } from 'zustand'

import api from '../services/api'



const useViolationStore = create((set) => ({

    violations: [],

    total: 0,

    page: 1,

    pages: 1,

    loading: false,

    filters: {

        camera_id: '',

        violation_type: '',

        plate_text: '',

        date_from: '',

        date_to: '',

    },



    setFilter: (key, value) => {

        set((s) => ({

            filters: { ...s.filters, [key]: value },

            page: 1,

        }))

    },



    clearFilters: () => {

        set({

            filters: {

                camera_id: '',

                violation_type: '',

                plate_text: '',

                date_from: '',

                date_to: '',

            },

            page: 1,

        })

    },



    setPage: (page) => set({ page }),



    fetchViolations: async () => {

        const state = useViolationStore.getState()

        set({ loading: true })



        const params = { page: state.page, per_page: 20 }

        if (state.filters.camera_id) params.camera_id = state.filters.camera_id

        if (state.filters.violation_type) params.violation_type = state.filters.violation_type

        if (state.filters.plate_text) params.plate_text = state.filters.plate_text

        if (state.filters.date_from) params.date_from = state.filters.date_from

        if (state.filters.date_to) params.date_to = state.filters.date_to



        try {

            const res = await api.get('/api/violations', { params })

            set({

                violations: res.data.items,

                total: res.data.total,

                page: res.data.page,

                pages: res.data.pages,

                loading: false,

            })

        } catch (err) {

            set({ loading: false })

        }

    },



    deleteViolation: async (id) => {

        await api.delete(`/api/violations/${id}`)

        // Refetch

        useViolationStore.getState().fetchViolations()

    },

}))



export default useViolationStore


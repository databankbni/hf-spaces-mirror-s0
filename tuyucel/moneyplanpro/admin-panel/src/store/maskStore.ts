import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface MaskState {
    isMasked: boolean;
    toggleMasking: () => void;
    setMasked: (val: boolean) => void;
}

export const useMaskStore = create<MaskState>()(
    persist(
        (set) => ({
            isMasked: true, // Masked by default for safety
            toggleMasking: () => set((state) => ({ isMasked: !state.isMasked })),
            setMasked: (val: boolean) => set({ isMasked: val }),
        }),
        {
            name: 'admin-mask-storage',
        }
    )
);

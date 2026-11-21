import React from 'react';
import {
	AbsoluteFill,
	interpolate,
	spring,
	useCurrentFrame,
	useVideoConfig,
	Easing,
} from 'remotion';

// Sem fontes da internet: usa as fontes do próprio Windows.
const FONTE = '"Segoe UI", Arial, sans-serif';
const PALAVRAS = ['Conexão', 'Família', 'Torralles'];

export const ConexaoFamilia: React.FC = () => {
	const frame = useCurrentFrame();
	const {fps, durationInFrames} = useVideoConfig();

	// Fundo: degradê que gira devagar o vídeo inteiro.
	const angulo = interpolate(frame, [0, durationInFrames], [160, 220]);

	// Saída suave no último segundo.
	const saida = interpolate(
		frame,
		[durationInFrames - 30, durationInFrames],
		[1, 0],
		{extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
	);

	// Linha dourada que cresce depois das palavras.
	const linha = interpolate(frame, [70, 110], [0, 1], {
		extrapolateLeft: 'clamp',
		extrapolateRight: 'clamp',
		easing: Easing.out(Easing.cubic),
	});

	// Leve aproximação contínua (efeito de câmera).
	const zoom = interpolate(frame, [0, durationInFrames], [1, 1.06]);

	return (
		<AbsoluteFill
			style={{
				background: `linear-gradient(${angulo}deg, #0f2a3d 0%, #1d4e5f 55%, #c9a227 140%)`,
				justifyContent: 'center',
				alignItems: 'center',
				fontFamily: FONTE,
			}}
		>
			<div
				style={{
					display: 'flex',
					flexDirection: 'column',
					alignItems: 'center',
					gap: 24,
					transform: `scale(${zoom})`,
					opacity: saida,
				}}
			>
				{PALAVRAS.map((palavra, i) => {
					const entrada = spring({
						frame: frame - 10 - i * 15,
						fps,
						config: {damping: 14, stiffness: 120, mass: 0.8},
					});
					return (
						<div
							key={palavra}
							style={{
								color: i === 2 ? '#f2d16b' : '#ffffff',
								fontSize: i === 2 ? 150 : 130,
								fontWeight: 800,
								letterSpacing: -2,
								lineHeight: 1.05,
								opacity: entrada,
								transform: `translateY(${(1 - entrada) * 80}px)`,
								textShadow: '0 8px 30px rgba(0,0,0,0.35)',
							}}
						>
							{palavra}
						</div>
					);
				})}
				<div
					style={{
						marginTop: 30,
						height: 10,
						width: 520 * linha,
						borderRadius: 5,
						background: '#f2d16b',
					}}
				/>
			</div>
		</AbsoluteFill>
	);
};
